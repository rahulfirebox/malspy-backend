import hashlib
import logging

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger("apps.api_keys")


class ApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Api-Key "):
            raw_key = auth[len("Api-Key ") :]
        else:
            raw_key = request.META.get("HTTP_X_API_KEY", "").strip() or None
        if not raw_key:
            return None

        from apps.api_keys.models import ApiKey

        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        try:
            key_obj = ApiKey.objects.select_related(
                "organization", "organization__plan", "created_by"
            ).get(
                key_hash=key_hash,
                revoked=False,
                deleted_at__isnull=True,
            )
        except ApiKey.DoesNotExist:
            raise AuthenticationFailed("Invalid or revoked API key.")

        org = key_obj.organization
        if not org.is_active:
            raise AuthenticationFailed("Organization is suspended.")

        plan = getattr(org, "plan", None)
        if not plan or not plan.api_access:
            raise AuthenticationFailed("Plan does not support API key access.")

        if key_obj.expires_at is not None and key_obj.expires_at < timezone.now():
            raise AuthenticationFailed("API key has expired.")

        try:
            key_obj.last_used_at = timezone.now()
            key_obj.save(update_fields=["last_used_at"])
        except Exception as exc:
            logger.warning("ApiKeyAuthentication: failed to update last_used_at: %s", exc)

        return (key_obj.created_by, key_obj)

    def authenticate_header(self, request):
        return "Api-Key"
