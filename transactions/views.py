from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, ListView, View
from .models import TransactionsModel, UserBankAccount
from .forms import DepositForm, WithdrawForm, LoanRequestForm, BalanceTransferForm
from django.contrib import messages
from django.urls import reverse_lazy
from django.http import HttpResponse
from datetime import datetime
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_email_to_user(subject, user, amount, template):
    subject = subject
    message = render_to_string(template, {"user": user, "amount": amount})
    send_email = EmailMultiAlternatives(subject, message, to=[user.email])
    send_email.attach_alternative(message, "text/html")
    send_email.send()


# Create your views here.
class TransactionCreateMixin(LoginRequiredMixin, CreateView):
    model = TransactionsModel
    success_url = reverse_lazy("home")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"account": self.request.user.account})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class DepositMoneyView(TransactionCreateMixin):
    template_name = "transactions/deposit_form.html"
    form_class = DepositForm

    def get_initial(self):
        initial = {"transaction_type": 1}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get("amount")
        account = self.request.user.account
        account.balance += amount
        account.save(update_fields=["balance"])

        messages.success(
            self.request, f"{amount}$ is deposited to your account successfully"
        )

        send_email_to_user(
            subject="Deposit Message",
            user=self.request.user,
            amount=amount,
            template="transactions/deposit_mail.html",
        )

        return super().form_valid(form)


class WithdrawMoneyView(TransactionCreateMixin):
    template_name = "transactions/withdraw_form.html"
    form_class = WithdrawForm

    def get_initial(self):
        initial = {"transaction_type": 2}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get("amount")
        account = self.request.user.account
        
        if account.is_bankrupt:
            messages.error(self.request, "This account is currently bankrupt and cannot perform this operation")
            return self.form_invalid(form)

        messages.success(self.request, f"{amount}$ withdrawn successfully")
        
        account.balance -= amount
        account.save(update_fields=["balance"])
        
        send_email_to_user(
            subject="Withdrawal Message",
            user=self.request.user,
            amount=amount,
            template="transactions/withdraw_mail.html",
        )

        return super().form_valid(form)


class LoanRequestView(TransactionCreateMixin):
    template_name = "transactions/loan_request_form.html"
    form_class = LoanRequestForm

    def get_initial(self):
        initial = {"transaction_type": 3}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get("amount")
        current_loan_count = TransactionsModel.objects.filter(
            account=self.request.user.account, transaction_type=3, loan_approve=True
        ).count()
        if current_loan_count >= 3:
            return HttpResponse("You Have crossed you loan limits")
        messages.success(self.request, f"Loan Request for {amount}$ successfully")

        send_email_to_user(
            subject="Loan Request Message",
            user=self.request.user,
            amount=amount,
            template="transactions/loan_request_mail.html",
        )

        return super().form_valid(form)


class TransactionReportView(LoginRequiredMixin, ListView):
    template_name = "transactions/transaction_report.html"
    model = TransactionsModel

    def get_queryset(self):
        queryset = super().get_queryset().filter(account=self.request.user.account)

        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")

        if start_date and end_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            queryset = queryset.filter(
                timestamps__date__gte=start_date, timestamps__date__lte=end_date
            )

            self.balance = TransactionsModel.objects.filter(
                timestamps__date__gte=start_date, timestamps__date__lte=end_date
            ).aggregate(Sum("amount"))

        else:
            self.balance = self.request.user.account.balance

        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"amount": self.request.user.account})
        return context


class LoanListView(LoginRequiredMixin, ListView):
    model = TransactionsModel
    template_name = "transactions/loan_request_list.html"
    context_object_name = "loans"

    def get_queryset(self):
        user_account = self.request.user.account
        queryset = TransactionsModel.objects.filter(
            account=user_account, transaction_type=3
        )
        return queryset


class PayLoanView(LoginRequiredMixin, View):
    def get(self, request, loan_id):
        loan = get_object_or_404(TransactionsModel, id=loan_id)
        if loan.loan_approve:
            user_account = loan.account
            if loan.amount < user_account.balance:
                user_account.balance -= loan.amount
                loan.balance_after_transactions = user_account.balance
                user_account.save()
                loan.loan_approve = True
                loan.transaction_type = 4
                loan.save()
                return redirect("loan_list")
            else:
                messages.error(f"Loan amount is greater than account balance")
        return redirect("loan_list")


class BalanceTransferView(TransactionCreateMixin):
    template_name = "transactions/balance_transfer_form.html"
    form_class = BalanceTransferForm

    def get_initial(self):
        initial = {"transaction_type": 5}
        return initial

    def form_valid(self, form):
        receiver_account_number = form.cleaned_data.get("receiver_account_number")
        amount = form.cleaned_data.get("amount")

        sender_account = self.request.user.account
        
        if amount > sender_account.balance:
            messages.error(self.request, "Insufficient Balance")
            return self.form_invalid(form)
        
        receiver_account = UserBankAccount.objects.filter(account_number=receiver_account_number).first()

        if not receiver_account:
            messages.error(self.request, "Receiver account does not exist")
            return self.form_invalid(form)
        
        if receiver_account_number == sender_account.account_number:
            messages.error(self.request, "You can not transfer money own account")
            return self.form_invalid(form)
        

        if sender_account.balance >= amount:
            sender_account.balance -= amount
            receiver_account.balance += amount

            TransactionsModel.objects.create(
                account=sender_account,
                amount=amount,
                balance_after_transactions=sender_account.balance,
                transaction_type=5,
            )

            TransactionsModel.objects.create(
                account=receiver_account,
                amount=amount,
                balance_after_transactions=receiver_account.balance,
                transaction_type=6,
            )

            sender_account.save(update_fields=["balance"])
            receiver_account.save(update_fields=["balance"])
            
            messages.success(self.request, "Transfer successful")
            
        return redirect("balance_transfer")
