from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):

    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.Select(
                choices=[(5, "5 — Slapper"), (4, "4 — Great"), (3, "3 — Fine"), (2, "2 — Meh"), (1, "1 — Nope")],
                attrs={"class": "form-input"},
            ),
            "comment": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 4,
                    "maxlength": 500,
                    "placeholder": "How was it? (max 500 characters)",
                }
            ),
        }
        labels = {"rating": "Rating", "comment": "Comment"}
