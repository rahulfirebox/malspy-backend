import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0002_initial"),
        ("domains", "0002_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServerAgent",
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
                ("name", models.CharField(max_length=200)),
                (
                    "agent_type",
                    models.CharField(
                        choices=[
                            ("wordpress_plugin", "WordPress Plugin"),
                            ("php_script", "PHP Script"),
                            ("python_script", "Python Script"),
                        ],
                        default="python_script",
                        max_length=30,
                    ),
                ),
                (
                    "token_hash",
                    models.CharField(db_index=True, max_length=64, unique=True),
                ),
                ("token_prefix", models.CharField(max_length=20)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("inactive", "Inactive"),
                            ("error", "Error"),
                        ],
                        db_index=True,
                        default="inactive",
                        max_length=20,
                    ),
                ),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "agent_version",
                    models.CharField(blank=True, max_length=20, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agents",
                        to="accounts.organization",
                    ),
                ),
                (
                    "domain",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agents",
                        to="domains.domain",
                    ),
                ),
            ],
            options={"db_table": "server_agents", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ServerScanResult",
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
                ("files_scanned", models.IntegerField(default=0)),
                ("files_infected", models.IntegerField(default=0)),
                ("findings", models.JSONField(default=list)),
                ("scan_duration_ms", models.IntegerField(default=0)),
                ("malware_found", models.BooleanField(default=False)),
                (
                    "agent_version",
                    models.CharField(blank=True, max_length=20, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "agent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scan_results",
                        to="agents.serveragent",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="server_scan_results",
                        to="accounts.organization",
                    ),
                ),
            ],
            options={"db_table": "server_scan_results", "ordering": ["-created_at"]},
        ),
    ]
