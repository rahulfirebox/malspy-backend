

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        (
            "accounts",
            "0007_organization_created_by_updated_by_user_created_by_updated_by",
        ),
    ]


    operations = [
        migrations.RemoveField(
            model_name="organization",
            name="created_by",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="updated_by",
        ),
        migrations.RemoveField(
            model_name="user",
            name="created_by",
        ),
        migrations.RemoveField(
            model_name="user",
            name="updated_by",
        ),
        migrations.AddField(
            model_name="organization",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("owner", "Owner"),
                    ("admin", "Admin"),
                    ("member", "Member"),
                    ("viewer", "Viewer"),
                    ("superadmin", "Superadmin"),
                ],
                db_index=True,
                default="admin",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="EmailVerificationToken",
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
                    "token_hash",
                    models.CharField(db_index=True, max_length=64, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_verification_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "email_verification_tokens",
                "ordering": ["-created_at"],
            },
        ),
    ]
