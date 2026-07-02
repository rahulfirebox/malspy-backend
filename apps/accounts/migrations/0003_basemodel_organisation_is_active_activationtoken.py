from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_initial"),
    ]

    operations = [

        migrations.AddField(
            model_name="organization",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),

        migrations.AddField(
            model_name="organization",
            name="is_active",
            field=models.BooleanField(default=True),
        ),

        migrations.AddField(
            model_name="user",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),

        migrations.AddField(
            model_name="passwordresettoken",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),

        migrations.AddField(
            model_name="passwordresettoken",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),

        migrations.CreateModel(
            name="ActivationToken",
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
                ("token", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activation_token",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "activation_tokens",
            },
        ),
    ]
