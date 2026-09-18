from django import forms
from django.contrib.auth.models import User

from home.models import TruckLocation
from menu.models import MenuItem

from .permissions import MANAGER_GROUPS


class MenuItemForm(forms.ModelForm):
    """Item editor. Slug and photo are admin-only."""

    class Meta:
        model = MenuItem
        fields = ["name", "description", "price", "prep_minutes", "category", "is_spicy", "is_available"]

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price < 0:
            raise forms.ValidationError("Price can't be negative.")
        return price


class TruckForm(forms.ModelForm):
    """Truck details. is_live has its own switch."""

    class Meta:
        model = TruckLocation
        fields = ["name", "zone", "trading_from", "trading_until", "ready_minutes", "slot_capacity"]
        widgets = {
            "trading_from": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
            "trading_until": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        }

    def clean_slot_capacity(self):
        cap = self.cleaned_data["slot_capacity"]
        if cap < 1:
            raise forms.ValidationError("A window needs room for at least one order.")
        return cap


class InviteForm(forms.Form):
    """Add a staff account."""

    ROLE_CHOICES = [("Crew", "Crew")] + [(name, name) for name in MANAGER_GROUPS]

    name = forms.CharField(max_length=150)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=ROLE_CHOICES, initial="Crew")

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Someone with that email is already on the list.")
        return email
