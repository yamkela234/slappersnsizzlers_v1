from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Avg
from django.templatetags.static import static
from django.urls import reverse


class Category(models.Model):
    """A menu section such as Burgers or Wings."""

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    """One thing you can order."""

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="items",
    )
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=7, decimal_places=2)
    image = models.ImageField(upload_to="menu/", blank=True)
    static_image = models.CharField(max_length=80, blank=True)  # bundled photo in static/img/, used when no upload exists
    prep_minutes = models.PositiveSmallIntegerField(default=15)
    is_spicy = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category__sort_order", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("menu.show", kwargs={"slug": self.slug})

    @property
    def image_url(self):
        """Uploaded photo if there is one, else the bundled static photo."""
        if self.image:
            return self.image.url
        return static("img/" + (self.static_image or "burger.jpg"))

    def requires_choice(self):
        """True if any option group is required."""
        return any(group.required for group in self.option_groups.all())

    def prep_range(self):
        """"12-15 min" from the stored estimate: a range sets an expectation a
        single number would keep breaking."""
        return f"{max(self.prep_minutes - 3, 1)}-{self.prep_minutes} min"

    def average_rating(self):
        """Mean of all ratings for this item, or None if nobody has reviewed it yet."""
        result = self.reviews.filter(is_hidden=False).aggregate(average=Avg("rating"))
        return result["average"]

    def review_count(self):
        """How many reviews this item has."""
        return self.reviews.filter(is_hidden=False).count()


class OptionGroup(models.Model):
    """A choice on a dish, e.g. 'Choose Sauce' (required) or 'Add Extras' (paid)."""

    food = models.ForeignKey(
        "MenuItem",
        on_delete=models.CASCADE,
        related_name="option_groups",
    )
    name = models.CharField(max_length=60)
    required = models.BooleanField(default=False)
    max_choices = models.PositiveSmallIntegerField(default=1)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.food}: {self.name}"

    def is_single(self):
        """Radios or checkboxes."""
        return self.max_choices <= 1

    def is_free(self):
        """True if no option in the group has a price."""
        return all(option.price_delta == 0 for option in self.options.all())


class Option(models.Model):
    """One row inside a group: "Peri-Peri" (R0) or "Bacon bits" (+R12)."""

    group = models.ForeignKey(OptionGroup, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=60)
    price_delta = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name + (f" (+R{self.price_delta})" if self.price_delta else "")


class Review(models.Model):
    """One user's review of one item; unique per (item, user)."""

    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        unique_together = ("menu_item", "user")
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.user} on {self.menu_item}: {self.rating}/5"
