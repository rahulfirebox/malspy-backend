

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0002_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MalwareSignature",
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
                    "signature_id",
                    models.CharField(db_index=True, max_length=20, unique=True),
                ),
                ("name", models.CharField(max_length=200)),
                (
                    "layer",
                    models.CharField(
                        choices=[
                            ("static", "Static"),
                            ("browser", "Browser"),
                            ("server", "Server"),
                        ],
                        db_index=True,
                        max_length=10,
                    ),
                ),
                ("pattern", models.TextField()),
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
                ("type", models.CharField(db_index=True, max_length=50)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("auto_updated", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "malware_signatures",
                "ordering": ["signature_id"],
            },
        ),
        migrations.CreateModel(
            name="Scan",
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
                ("url", models.CharField(max_length=2000)),
                ("domain", models.CharField(db_index=True, max_length=500)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("scanning", "Scanning"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=20,
                    ),
                ),
                ("is_public", models.BooleanField(db_index=True, default=False)),
                (
                    "overall_rating",
                    models.CharField(
                        blank=True, db_index=True, max_length=1, null=True
                    ),
                ),
                ("malware_detected", models.BooleanField(db_index=True, default=False)),
                ("blacklisted", models.BooleanField(db_index=True, default=False)),
                ("sucuri_raw", models.JSONField(blank=True, null=True)),
                ("site_info", models.JSONField(blank=True, null=True)),
                ("tls_info", models.JSONField(blank=True, null=True)),
                ("tls_direct_info", models.JSONField(blank=True, null=True)),
                ("whois_info", models.JSONField(blank=True, null=True)),
                ("recommendations", models.JSONField(blank=True, null=True)),
                ("blacklist_info", models.JSONField(blank=True, null=True)),
                ("links_info", models.JSONField(blank=True, null=True)),
                ("ratings_info", models.JSONField(blank=True, null=True)),
                ("software_info", models.JSONField(blank=True, null=True)),
                ("malware_info", models.JSONField(blank=True, null=True)),
                ("browser_scan_info", models.JSONField(blank=True, null=True)),
                ("scan_duration_ms", models.IntegerField(blank=True, null=True)),
                ("notify_email", models.BooleanField(default=True)),
                ("was_cached", models.BooleanField(default=False)),
                ("cache_source_id", models.UUIDField(blank=True, null=True)),
                ("parent_scan_id", models.UUIDField(blank=True, null=True)),
                (
                    "deleted_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scans",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scans",
                        to="accounts.organization",
                    ),
                ),
            ],
            options={
                "db_table": "scans",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["organization", "status"],
                        name="scans_organiz_4010a8_idx",
                    ),
                    models.Index(
                        fields=["organization", "domain"],
                        name="scans_organiz_9b331d_idx",
                    ),
                    models.Index(
                        fields=["organization", "created_at"],
                        name="scans_organiz_f5157a_idx",
                    ),
                    models.Index(
                        fields=["organization", "overall_rating"],
                        name="scans_organiz_640444_idx",
                    ),
                ],
            },
        ),
    ]
