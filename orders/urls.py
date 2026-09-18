from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="orders.index"),
    path("checkout/", views.checkout, name="orders.checkout"),
    path("<int:order_id>/", views.show, name="orders.show"),
    path("<int:order_id>/status.json", views.status_json, name="orders.status_json"),
    path("<int:order_id>/confirmation/", views.confirmation, name="orders.confirmation"),
]
