from django.contrib.auth import login, logout
from django.db.models.base import Model as Model
from django.contrib.auth import update_session_auth_hash
from django.http import HttpResponse
from django.views.generic import FormView, UpdateView
from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.contrib import messages
from .forms import UserRegistrationForm, UpdateUserForm, ChangeUserPasswordFrom
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

def send_email_to_user(subject, user, template):
    subject = subject
    message = render_to_string(template, {"user": user})
    send_email = EmailMultiAlternatives(subject, message, to=[user.email])
    send_email.attach_alternative(message, "text/html")
    send_email.send()

class UserRegistrationView(FormView):
    form_class = UserRegistrationForm
    template_name = "accounts/user_registration.html"
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        return super().form_valid(form)


class UserLoginView(LoginView):
    template_name = "accounts/user_login.html"

    def get_success_url(self) -> str:
        return reverse_lazy("home")


class UserLogoutView(LogoutView):
    def get_success_url(self) -> str:
        if self.request.user.is_authenticated:
            logout(self.request)
        return reverse_lazy("home")


class UpdateUserProfileView(UpdateView):
    form_class = UpdateUserForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("profile")

    def get_object(self, queryset=None):
        return self.request.user
    

class ChangeUserPasswordView(PasswordChangeView):
    template_name = "accounts/change_password.html"
    form_class = ChangeUserPasswordFrom

    def form_valid(self, form):
        send_email_to_user(
            subject="Password Change Message",
            user=self.request.user,
            template="accounts/password_mail.html",
        )
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse_lazy("profile")