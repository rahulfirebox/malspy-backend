from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0005_plan_quota_check_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="price_yearly",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
            ),
        ),
    ]
