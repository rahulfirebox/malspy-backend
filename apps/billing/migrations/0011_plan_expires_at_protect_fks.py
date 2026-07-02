from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_remove_organization_created_by_and_more"),
        ("billing", "0010_fix_plan_quotas"),
    ]

    operations = [
        migrations.AlterField(
            model_name="subscription",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subscriptions",
                to="accounts.organization",
            ),
        ),
        migrations.AlterField(
            model_name="invoice",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="invoices",
                to="accounts.organization",
            ),
        ),
    ]
