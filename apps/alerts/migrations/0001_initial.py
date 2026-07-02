

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Alert",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "deleted_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("malware_detected", "Malware Detected"),
                            ("blacklisted", "Blacklisted"),
                            ("tls_expiring", "TLS Expiring"),
                            ("rating_degraded", "Rating Degraded"),
                            ("missing_headers", "Missing Headers"),
                        ],
                        db_index=True,
                        max_length=30,
                    ),
                ),
                (
                    "severity",
                    models.CharField(
                        choices=[
                            ("critical", "Critical"),
                            ("high", "High"),
                            ("medium", "Medium"),
                            ("low", "Low"),
                        ],
                        db_index=True,
                        max_length=10,
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("is_resolved", models.BooleanField(db_index=True, default=False)),
                ("resolved_note", models.TextField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "alerts",
                "ordering": ["-created_at"],
            },
        ),
    ]
