from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0006_fix_alert_constraint_and_scan_nonnull"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alert",
            name="type",
            field=models.CharField(
                choices=[
                    ("malware_detected", "Malware Detected"),
                    ("blacklisted", "Blacklisted"),
                    ("tls_expiring", "TLS Expiring"),
                    ("missing_headers", "Missing Headers"),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]
