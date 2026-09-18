from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from orders.utils import has_collected_item

from .forms import ReviewForm
from .models import MenuItem, Option, Review
from .suggestions import suggestions_for


def index(request):
    """/menu/ redirects to the menu section on the home page."""
    return redirect(reverse("home.index") + "#menu", permanent=True)


def show(request, slug):
    """Item detail: rating summary, reviews and the review form."""
    item = get_object_or_404(MenuItem, slug=slug)
    reviews = item.reviews.filter(is_hidden=False).select_related("user")
    user_review = None
    form = None
    if request.user.is_authenticated:
        user_review = item.reviews.filter(user=request.user).first()
        if user_review is None and has_collected_item(request.user, item):
            form = ReviewForm()
    return render(request, "menu/show.html", {
        "item": item,
        "groups": _option_groups(item),
        "selected_ids": _selected_ids(request),
        "initial_qty": _initial_qty(request),
        "initial_note": request.GET.get("note", "")[:200],
        "suggestions": suggestions_for([item]),
        "reviews": reviews,
        "average_rating": item.average_rating(),
        "review_count": item.review_count(),
        "user_review": user_review,
        "form": form,
    })


def _option_groups(item):
    """The item's groups with only available options."""
    return item.option_groups.prefetch_related(Prefetch("options", queryset=Option.objects.filter(is_available=True)))


def _selected_ids(request):
    """?opt=3&opt=9 → {3, 9}. The cart links a line back to its dish with the
    chosen option ids in the query string so the pickers reopen as they were."""
    return {int(raw) for raw in request.GET.getlist("opt") if raw.isdigit()}


def _initial_qty(request):
    try:
        return max(1, min(int(request.GET.get("qty", 1)), 10))
    except (TypeError, ValueError):
        return 1


@login_required
def review_create(request, slug):
    """Handle the review form posted from the item page."""
    item = get_object_or_404(MenuItem, slug=slug)
    if request.method != "POST":
        return redirect(item)
    if item.reviews.filter(user=request.user).exists():
        messages.warning(request, "You've already reviewed this item — edit your existing review instead.")
        return redirect(item)
    if not has_collected_item(request.user, item):
        messages.warning(request, "Reviews are for dishes you've ordered and collected — order it first!")
        return redirect(item)
    form = ReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        review.menu_item = item
        review.user = request.user
        review.save()
        messages.success(request, "Thanks — your review is live.")
        return redirect(item)
    messages.error(request, "Please fix the errors in your review.")
    return render(request, "menu/show.html", {
        "item": item,
        "groups": _option_groups(item),
        "selected_ids": set(),
        "initial_qty": 1,
        "initial_note": "",
        "suggestions": suggestions_for([item]),
        "reviews": item.reviews.filter(is_hidden=False).select_related("user"),
        "average_rating": item.average_rating(),
        "review_count": item.review_count(),
        "user_review": None,
        "form": form,
    })


@login_required
def review_edit(request, slug, review_id):
    """Let the AUTHOR of a review change it. Anyone else gets 403."""
    review = get_object_or_404(Review, pk=review_id, menu_item__slug=slug)
    if review.user != request.user:
        raise PermissionDenied
    if request.method == "POST":
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            messages.success(request, "Your review was updated.")
            return redirect(review.menu_item)
    else:
        form = ReviewForm(instance=review)
    return render(request, "menu/review_form.html", {
        "form": form,
        "review": review,
        "item": review.menu_item,
    })


@login_required
def review_delete(request, slug, review_id):
    """GET shows a confirmation, POST deletes."""
    review = get_object_or_404(Review, pk=review_id, menu_item__slug=slug)
    if review.user != request.user:
        raise PermissionDenied
    if request.method == "POST":
        item = review.menu_item
        review.delete()
        messages.success(request, "Your review was deleted.")
        return redirect(item)
    return render(request, "menu/review_confirm_delete.html", {
        "review": review,
        "item": review.menu_item,
    })
