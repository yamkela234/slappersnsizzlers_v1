from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User


class SignUpForm(UserCreationForm):
    """UserCreationForm with a required email field."""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "class": "form-input",
            "placeholder": "you@example.com",
        }),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"class": "form-input", "placeholder": "Choose a username"}
        )
        for name in ("password1", "password2"):
            self.fields[name].widget.attrs.update({"class": "form-input"})
        self.fields["password1"].widget.attrs["placeholder"] = "Password"
        self.fields["password2"].widget.attrs["placeholder"] = "Repeat password"


class LoginForm(AuthenticationForm):
    """AuthenticationForm with the site's input classes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"class": "form-input", "placeholder": "Username", "autofocus": True}
        )
        self.fields["password"].widget.attrs.update(
            {"class": "form-input", "placeholder": "Password"}
        )
