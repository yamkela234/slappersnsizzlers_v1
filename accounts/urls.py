from django.urls import path
from . import views

urlpatterns = [
    path("signup/", views.signup, name="accounts.signup"),
    path("login/", views.login_view, name="accounts.login"),
    path("logout/", views.logout_view, name="accounts.logout"),
]
