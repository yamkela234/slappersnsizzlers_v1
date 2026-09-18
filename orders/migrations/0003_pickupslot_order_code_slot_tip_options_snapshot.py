"""
Add PickupSlot, Order.code/slot/tip, and rename sauce_snapshot to options_snapshot.
"""

import secrets
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def mint_codes(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    for order in Order.objects.filter(code=""):
        order.code = f"{secrets.randbelow(9000) + 1000}"
        order.save(update_fields=["code"])


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_orderitem_note_orderitem_sauce_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="PickupSlot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start", models.DateTimeField(unique=True)),
                ("capacity", models.PositiveSmallIntegerField(default=8)),
                ("taken", models.PositiveSmallIntegerField(default=0)),
            ],
            options={"ordering": ["start"]},
        ),
        migrations.AddField(
            model_name="order",
            name="code",
            field=models.CharField(blank=True, max_length=4),
        ),
        migrations.RunPython(mint_codes, migrations.RunPython.noop),
        migrations.AddField(
            model_name="order",
            name="slot",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="orders", to="orders.pickupslot"),
        ),
        migrations.AddField(
            model_name="order",
            name="tip",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=6),
        ),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(choices=[("pending", "Pending"), ("preparing", "Preparing"), ("ready", "Ready"), ("collected", "Collected"), ("cancelled", "Cancelled")], default="pending", max_length=10),
        ),
        migrations.RenameField(
            model_name="orderitem",
            old_name="sauce_snapshot",
            new_name="options_snapshot",
        ),
        migrations.AlterField(
            model_name="orderitem",
            name="options_snapshot",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
