import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_plan_basemodel_subscription_constraints"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessedWebhookEvent",
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
                (
                    "event_id",
                    models.CharField(db_index=True, max_length=255, unique=True),
                ),
                (
                    "processed_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
            ],
            options={
                "db_table": "processed_webhook_events",
            },
        ),
    ]
