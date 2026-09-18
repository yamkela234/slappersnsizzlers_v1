from decimal import Decimal

from django import forms

TIP_AMOUNT = Decimal("10.00")


class CheckoutForm(forms.Form):
    """Contact details and the optional tip. Everything else comes from the session."""

    customer_name = forms.CharField(
        max_length=80,
        widget=forms.TextInput(attrs={
            "class": "form-input", "placeholder": "Name for collection", "autocomplete": "name",
        }),
    )
    phone = forms.CharField(
        max_length=20,
        min_length=7,
        widget=forms.TextInput(attrs={
            "class": "form-input", "placeholder": "e.g. 082 123 4567", "autocomplete": "tel", "inputmode": "tel",
        }),
    )
    tip = forms.BooleanField(
        required=False,
        initial=False,
    )

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        allowed = set("0123456789+ -()")
        if not set(phone) <= allowed:
            raise forms.ValidationError("Enter a phone number using digits only (spaces, +, - are fine).")
        if sum(ch.isdigit() for ch in phone) < 7:
            raise forms.ValidationError("That number looks too short.")
        return phone

    def tip_amount(self):
        """The Decimal the order stores."""
        return TIP_AMOUNT if self.cleaned_data.get("tip") else Decimal("0.00")
