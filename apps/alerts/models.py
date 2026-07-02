from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class Alert(BaseModel):
    def delete(self, using=None, keep_parents=False):

        return (0, {})

    def soft_delete(self):

        return

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="alerts",
        db_index=True,
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )
    scan = models.ForeignKey(
        "scans.Scan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )
    type = models.CharField(
        max_length=30,
        choices=[
            ("malware_detected", "Malware Detected"),
            ("blacklisted", "Blacklisted"),
            ("tls_expiring", "TLS Expiring"),
            ("missing_headers", "Missing Headers"),
        ],
        db_index=True,
    )
    severity = models.CharField(
        max_length=10,
        choices=[
            ("critical", "Critical"),
            ("high", "High"),
            ("medium", "Medium"),
            ("low", "Low"),
        ],
        db_index=True,
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False, db_index=True)
    resolved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_alerts",
    )
    resolved_note = models.TextField(blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts_created",
    )
    updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts_updated",
    )

    class Meta:
        db_table = "alerts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "is_resolved"]),
            models.Index(fields=["organization", "severity"]),
            models.Index(fields=["organization", "type"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "domain", "type"],
                condition=Q(is_resolved=False) & Q(deleted_at__isnull=True),
                name="unique_active_alert_per_type",
            ),
            models.CheckConstraint(
                check=Q(
                    type__in=[
                        "malware_detected",
                        "blacklisted",
                        "tls_expiring",
                        "missing_headers",
                    ]
                ),
                name="alert_type_valid",
            ),
            models.CheckConstraint(
                check=Q(severity__in=["critical", "high", "medium", "low"]),
                name="alert_severity_valid",
            ),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.title}"
