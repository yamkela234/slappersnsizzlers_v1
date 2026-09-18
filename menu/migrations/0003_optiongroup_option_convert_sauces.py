"""
Replace the Sauce M2M with OptionGroup/Option, converting existing sauces
into a required 'Choose Sauce' group per dish.
"""

from django.db import migrations, models
import django.db.models.deletion


def sauces_to_groups(apps, schema_editor):
    MenuItem = apps.get_model("menu", "MenuItem")
    OptionGroup = apps.get_model("menu", "OptionGroup")
    Option = apps.get_model("menu", "Option")
    for item in MenuItem.objects.all():
        sauces = list(item.sauces.all())  # the M2M still exists at this point — the RemoveField below runs after
        if not sauces:
            continue
        group = OptionGroup.objects.create(food=item, name="Choose Sauce", required=True, max_choices=1, sort_order=1)
        for sauce in sauces:
            Option.objects.create(group=group, name=sauce.name, price_delta=0, sort_order=sauce.sort_order, is_available=sauce.is_available)


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0002_sauce_menuitem_is_spicy_menuitem_prep_minutes_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="OptionGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60)),
                ("required", models.BooleanField(default=False)),
                ("max_choices", models.PositiveSmallIntegerField(default=1)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("food", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="option_groups", to="menu.menuitem")),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.CreateModel(
            name="Option",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60)),
                ("price_delta", models.DecimalField(decimal_places=2, default=0, max_digits=6)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("is_available", models.BooleanField(default=True)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="options", to="menu.optiongroup")),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.RunPython(sauces_to_groups, migrations.RunPython.noop),
        migrations.RemoveField(model_name="menuitem", name="sauces"),
        migrations.DeleteModel(name="Sauce"),
    ]
