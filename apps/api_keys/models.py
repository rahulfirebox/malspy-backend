from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class ApiKey(BaseModel):
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="api_keys",
        db_index=True,
    )
    name = models.CharField(max_length=200)
    key_hash = models.CharField(max_length=64, unique=True, db_index=True)
    key_prefix = models.CharField(max_length=20)
    revoked = models.BooleanField(default=False, db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="api_keys",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_api_keys",
    )

    class Meta:
        db_table = "api_keys"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                condition=Q(deleted_at__isnull=True),
                name="unique_apikey_name_per_org",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.key_prefix}...)"
