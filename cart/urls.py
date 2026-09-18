from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="cart.index"),
    path("add/<int:item_id>/", views.add, name="cart.add"),
    path("update/<str:line_key>/", views.update, name="cart.update"),
    path("remove/<str:line_key>/", views.remove, name="cart.remove"),
    path("clear/", views.clear, name="cart.clear"),
]
