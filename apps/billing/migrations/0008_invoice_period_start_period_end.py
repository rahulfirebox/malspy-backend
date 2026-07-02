from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0007_ledger_entry"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="period_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="invoice",
            name="period_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
