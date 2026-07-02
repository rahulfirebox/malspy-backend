

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Domain",
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
                ("domain", models.CharField(db_index=True, max_length=500)),
                (
                    "frequency",
                    models.CharField(
                        choices=[
                            ("daily", "Daily"),
                            ("weekly", "Weekly"),
                            ("monthly", "Monthly"),
                        ],
                        db_index=True,
                        default="daily",
                        max_length=10,
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "last_status",
                    models.CharField(
                        choices=[
                            ("clean", "Clean"),
                            ("infected", "Infected"),
                            ("blacklisted", "Blacklisted"),
                            ("unknown", "Unknown"),
                        ],
                        db_index=True,
                        default="unknown",
                        max_length=20,
                    ),
                ),
                (
                    "slack_webhook_url",
                    models.CharField(blank=True, max_length=500, null=True),
                ),
                ("notify_email", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "domains",
            },
        ),
    ]
