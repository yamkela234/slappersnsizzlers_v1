from django.urls import reverse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.http import require_POST

from .forms import SignUpForm, LoginForm


def signup(request):
    """Register a new user, log them in immediately, send them to the menu."""
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome, {user.username}! Your account is ready.")
            return redirect(reverse("home.index") + "#menu")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


def login_view(request):
    """Log an existing user in."""
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "You're signed in.")
            next_url = request.GET.get("next")
            return redirect(next_url or "home.index")
        messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm(request)
    return render(request, "accounts/login.html", {"form": form})


@require_POST
def logout_view(request):
    """Log the user out and send them home."""
    logout(request)
    messages.info(request, "You've been signed out. See you next time!")
    return redirect("home.index")
