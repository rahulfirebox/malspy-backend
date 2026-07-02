import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class ActiveAgentManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class ServerAgent(BaseModel):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("error", "Error"),
        ("revoked", "Revoked"),
    ]
    TYPE_CHOICES = [
        ("wordpress_plugin", "WordPress Plugin"),
        ("php_script", "PHP Script"),
        ("python_script", "Python Script"),
    ]

    objects = ActiveAgentManager()
    all_objects = models.Manager()

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="agents",
        db_index=True,
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_agents",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_agents",
    )
    name = models.CharField(max_length=200)
    agent_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default="python_script")
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    token_prefix = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="inactive", db_index=True
    )
    revoked = models.BooleanField(default=False, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_scan_at = models.DateTimeField(null=True, blank=True)
    agent_version = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        db_table = "server_agents"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                condition=Q(deleted_at__isnull=True),
                name="unique_active_agent_name_per_org",
            ),
            models.CheckConstraint(
                check=Q(status__in=["active", "inactive", "error", "revoked"]),
                name="agent_status_valid",
            ),
            models.CheckConstraint(
                check=Q(
                    agent_type__in=[
                        "wordpress_plugin",
                        "php_script",
                        "python_script",
                    ]
                ),
                name="agent_type_valid",
            ),
        ]

    @classmethod
    def generate_token(cls):
        raw = "sk_agent_" + secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        prefix = raw[:16]
        return raw, token_hash, prefix


class ServerScanResult(BaseModel):
    agent = models.ForeignKey(
        ServerAgent,
        on_delete=models.CASCADE,
        related_name="scan_results",
    )
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="server_scan_results",
        db_index=True,
    )
    files_scanned = models.IntegerField(default=0)
    files_infected = models.IntegerField(default=0)
    findings = models.JSONField(default=list)
    scan_duration_ms = models.IntegerField(default=0)
    malware_found = models.BooleanField(default=False)
    agent_version = models.CharField(max_length=20, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="completed",
        db_index=True,
    )
    scan_started_at = models.DateTimeField(null=True, blank=True)
    scan_completed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    server_path = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        db_table = "server_scan_results"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(status__in=["pending", "completed", "failed"]),
                name="server_scan_result_status_valid",
            ),
        ]
