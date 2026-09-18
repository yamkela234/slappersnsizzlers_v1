from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="menu.index"),
    path("<slug:slug>/", views.show, name="menu.show"),
    path("<slug:slug>/review/create/", views.review_create, name="menu.review_create"),
    path("<slug:slug>/review/<int:review_id>/edit/", views.review_edit, name="menu.review_edit"),
    path("<slug:slug>/review/<int:review_id>/delete/", views.review_delete, name="menu.review_delete"),
]
