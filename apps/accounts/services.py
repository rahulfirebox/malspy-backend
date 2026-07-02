import hashlib
import logging
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password as django_check_password
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import IntegrityError, OperationalError, ProgrammingError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import AuthenticationFailed, NotFound, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Organization, PasswordResetToken, User

logger = logging.getLogger(__name__)

_USER_UPDATE_ALLOWED_FIELDS: frozenset = frozenset(["name", "notify_email", "timezone"])

_ORG_UPDATE_ALLOWED_FIELDS: frozenset = frozenset(["name"])

_EMAIL_VERIFY_TTL = 86400


def register(data: dict) -> tuple:
    if not data.get("email"):
        raise ValidationError({"email": ["Email is required."]})

    email = data["email"].strip().lower()

    with transaction.atomic():

        existing_unverified = User.objects.filter(
            email__iexact=email, is_email_verified=False
        ).first()
        if existing_unverified:

            if existing_unverified.organization:
                existing_unverified.organization.delete()
            existing_unverified.delete()
        elif User.objects.filter(email__iexact=email).exists():
            raise ValidationError({"email": ["Email already registered."]})

        from apps.billing.models import Plan

        try:
            free_plan = Plan.objects.get(slug="free")
        except Plan.DoesNotExist:
            raise NotFound("Free plan not configured. Run seed_plans management command.")

        try:
            user = User.objects.create_user(
                email=email,
                name=data["name"],
                password=data["password"],
                role="owner",
                organization=None,
            )
        except IntegrityError:
            raise ValidationError({"email": ["Email already registered."]})

        org_name = (
            data.get("organization_name") or data.get("org_name") or ""
        ).strip() or f"{data['name']}'s Organization"
        base_slug = slugify(org_name)[:100]
        unique_suffix = str(uuid.uuid4())[:8]
        org_slug = f"{base_slug}-{unique_suffix}"

        org = Organization.objects.create(
            name=org_name,
            slug=org_slug,
            plan=free_plan,
            owner=user,
            quota_reset_at=timezone.now() + timedelta(days=30),
        )

        user.organization = org
        user.save(update_fields=["organization", "updated_at"])

        try:
            from apps.core.models import AuditLog

            AuditLog.objects.create(
                action="USER_REGISTERED",
                actor=user,
                organization=org,
                resource_type="user",
                resource_id=str(user.id),
                changes={"email": email, "org": org_name},
            )
        except ValidationError:
            raise
        except Exception as audit_exc:
            logger.warning(
                "AuditLog failed user_registered: %s",
                audit_exc,
                extra={"user_id": str(user.id), "org_id": str(org.id)},
            )

    raw_verify_token = secrets.token_urlsafe(32)
    transaction.on_commit(
        lambda: cache.set(
            f"email_verify:{raw_verify_token}", str(user.id), timeout=_EMAIL_VERIFY_TTL
        )
    )
    frontend_url = getattr(settings, "EMAIL_FRONTEND_DOMAIN", getattr(settings, "FRONTEND_URL", ""))
    try:
        send_mail(
            subject="Verify your Sucuri account email",
            message=(
                "Click the link to verify your email:\n"
                f"{frontend_url}/verify-email?token={raw_verify_token}\n\n"
                "This link expires in 24 hours."
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@sucuri.dev"),
            recipient_list=[email],
            fail_silently=True,
        )
    except ValidationError:
        raise
    except Exception as exc:
        logger.error(
            "Failed to send verification email to %s: %s",
            email,
            exc,
            extra={"user_id": str(user.id)},
        )

    return user, org


def verify_email(raw_token: str) -> User:
    cache_key = f"email_verify:{raw_token}"
    user_id = cache.get(cache_key)

    if not user_id:
        raise ValidationError(
            {"code": "INVALID_TOKEN", "detail": "Invalid or expired verification link."}
        )

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        from apps.core.exceptions import ResourceNotFound

        raise ResourceNotFound("Invalid or expired verification token.")
    except (OperationalError, ProgrammingError) as exc:
        logger.error("DB error in verify_email: %s", exc, extra={})
        raise ValidationError({"detail": "Service unavailable. Try again."})

    if not user.is_email_verified:
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified", "updated_at"])

    cache.delete(cache_key)
    return user


def login(email: str, password: str, request=None) -> dict:
    email = email.strip().lower()

    try:
        user = User.objects.filter(email__iexact=email).first()
    except (OperationalError, ProgrammingError) as exc:
        logger.error("DB error in login: %s", exc, extra={})
        raise ValidationError({"detail": "Service unavailable. Try again."})
    if user is None:
        django_check_password("dummy_equalize_timing", make_password("dummy"))
        raise ValidationError({"detail": "Invalid credentials."})

    if not django_check_password(password, user.password):
        raise ValidationError({"detail": "Invalid credentials."})

    if hasattr(user, "organization") and user.organization and not user.organization.is_active:
        raise AuthenticationFailed(
            {
                "code": "ORGANIZATION_SUSPENDED",
                "message": "Your organization has been suspended",
            }
        )

    if not user.is_active:
        raise AuthenticationFailed("Account is deactivated.")

    if not user.is_email_verified:
        raise AuthenticationFailed(
            {
                "code": "EMAIL_NOT_VERIFIED",
                "detail": "Please verify your email before logging in.",
            }
        )

    from apps.core.models import AuditLog

    try:
        AuditLog.objects.create(
            action="LOGIN",
            actor=user,
            organization=user.organization,
            resource_type="user",
            resource_id=str(user.id),
        )
    except ValidationError:
        raise
    except Exception as exc:
        logger.warning("AuditLog write failed in login: %s", exc, extra={"user_id": str(user.id)})

    if getattr(user, "mfa_enabled", False):
        raise ValidationError(
            {"code": "MFA_REQUIRED", "detail": "Multi-factor authentication is required."}
        )

    from .serializers import UserSerializer

    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSerializer(user).data,
    }


def logout(refresh_token: str) -> None:

    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
    except (OperationalError, ProgrammingError) as exc:
        logger.error("DB error during logout blacklist: %s", exc, extra={})
        raise ValidationError({"detail": "Logout failed. Token may still be active. Try again."})
    except ValidationError:
        raise
    except Exception as exc:
        logger.warning("Logout blacklist failed: %s", exc, extra={})


def create_password_reset_token(email: str) -> str | None:
    email = email.strip().lower()
    try:
        user = User.objects.get(email=email, is_active=True)
    except User.DoesNotExist:
        return None
    except (OperationalError, ProgrammingError) as exc:
        email_hash = hashlib.sha256(email.encode()).hexdigest()[:16]
        logger.error(
            "DB error in create_password_reset_token: %s",
            exc,
            extra={"email_hash": email_hash},
        )
        raise ValidationError({"detail": "Service temporarily unavailable."})

    raw = None
    for _attempt in range(3):
        try:
            _candidate = secrets.token_urlsafe(32)
            _token_hash = hashlib.sha256(_candidate.encode()).hexdigest()
            with transaction.atomic():
                PasswordResetToken.objects.create(
                    user=user,
                    token_hash=_token_hash,
                    bound_email=email,
                    purpose="password_reset",
                    expires_at=timezone.now() + timedelta(hours=1),
                )
            raw = _candidate
            break
        except IntegrityError:
            if _attempt == 2:
                raise ValidationError(
                    {"detail": "Unable to create password reset token. Try again."}
                )
        except (OperationalError, ProgrammingError) as exc:
            logger.error("DB error creating reset token: %s", exc, extra={"user_id": str(user.id)})
            raise ValidationError({"detail": "Service unavailable. Try again."})
        except ValidationError:
            raise
        except Exception as exc:
            logger.error("Failed to create reset token: %s", exc, extra={"user_id": str(user.id)})
            raise ValidationError({"detail": "Unable to create password reset token. Try again."})

    frontend_url = getattr(settings, "EMAIL_FRONTEND_DOMAIN", getattr(settings, "FRONTEND_URL", ""))
    try:
        send_mail(
            subject="Reset your Sucuri password",
            message=(
                "Click the link to reset your password:\n"
                f"{frontend_url}/reset-password?token={raw}\n\n"
                "This link expires in 1 hour."
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@sucuri.dev"),
            recipient_list=[email],
            fail_silently=True,
        )
    except ValidationError:
        raise
    except Exception as exc:
        logger.error(
            "Failed to send reset email to %s: %s",
            email,
            exc,
            extra={"user_id": str(user.id)},
        )

    return raw


def consume_password_reset_token(raw_token: str, new_password: str) -> User:
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    with transaction.atomic():
        try:
            record = (
                PasswordResetToken.objects.select_for_update()
                .filter(
                    token_hash=token_hash,
                    purpose="password_reset",
                    expires_at__gt=timezone.now(),
                    used_at__isnull=True,
                )
                .select_related("user")
                .first()
            )
        except (OperationalError, ProgrammingError) as exc:
            logger.error("DB error in consume_reset_token: %s", exc, extra={})
            raise ValidationError({"detail": "Service unavailable. Try again."})

        if record is None:
            raise ValidationError({"code": "INVALID_TOKEN", "detail": "Invalid or expired token."})

        if len(new_password) < 8:
            raise ValidationError({"password": ["Password must be at least 8 characters."]})

        record.used_at = timezone.now()
        record.save(update_fields=["used_at"])
        record.user.set_password(new_password)
        record.user.save(update_fields=["password", "updated_at"])

        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                BlacklistedToken,
                OutstandingToken,
            )

            from apps.core.models import AuditLog

            outstanding = OutstandingToken.objects.filter(user=record.user)

            BlacklistedToken.objects.bulk_create(
                [BlacklistedToken(token=t) for t in outstanding],
                batch_size=500,
                ignore_conflicts=True,
            )
            try:
                AuditLog.objects.create(
                    action="PASSWORD_RESET",
                    actor=record.user,
                    organization=record.user.organization,
                    resource_type="user",
                    resource_id=str(record.user.id),
                    changes={"tokens_blacklisted": True},
                )
            except Exception as audit_exc:
                logger.warning(
                    "AuditLog failed for password reset: %s",
                    audit_exc,
                    extra={"user_id": str(record.user.id)},
                )
        except (OperationalError, ProgrammingError) as exc:
            logger.error(
                "DB error blacklisting tokens after password reset: %s",
                exc,
                extra={"user_id": str(record.user.id)},
            )
            raise
        except ValidationError:
            raise
        except Exception as exc:
            logger.warning(
                "Failed to blacklist outstanding tokens after password reset: %s",
                exc,
                extra={},
            )

    return record.user


def update_profile(user: User, data: dict) -> User:
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        for field, value in data.items():
            if field not in _USER_UPDATE_ALLOWED_FIELDS:
                continue
            setattr(user, field, value)
        changed = [f for f in _USER_UPDATE_ALLOWED_FIELDS if f in data]
        if changed:
            user.save(update_fields=changed + ["updated_at"])
            try:
                from apps.core.models import AuditLog

                AuditLog.objects.create(
                    action="PROFILE_UPDATED",
                    actor=user,
                    organization=user.organization,
                    resource_type="user",
                    resource_id=str(user.id),
                    changes={"fields_updated": changed},
                )
            except ValidationError:
                raise
            except Exception as audit_exc:
                logger.warning(
                    "AuditLog failed profile_updated: %s",
                    audit_exc,
                    extra={"user_id": str(user.id)},
                )
    return user


def list_org_members(org: Organization, q: str | None = None):
    if not org:
        raise ValidationError({"detail": "Organization is required."})

    try:
        qs = (
            User.objects.filter(
                organization=org,
                is_active=True,
            )
            .select_related("organization")
            .order_by("-created_at")
        )

        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q))

        return qs
    except (OperationalError, ProgrammingError) as exc:
        logger.error(
            "DB error in list_org_members: %s",
            exc,
            extra={"org_id": str(org.id)},
        )
        raise ValidationError({"detail": "Service unavailable. Try again."})


def add_org_member(org: Organization, email: str, role: str, requesting_user) -> "User":
    if not org:
        raise ValidationError({"detail": "Organization is required."})

    email = email.strip().lower()
    allowed_roles = {"admin", "member", "viewer"}
    if role not in allowed_roles:
        raise ValidationError(
            {"role": [f"Role must be one of: {', '.join(sorted(allowed_roles))}."]}
        )

    with transaction.atomic():
        try:
            member = User.objects.select_for_update().get(email=email)
        except User.DoesNotExist:

            member = None
            for _attempt in range(3):
                try:
                    temp_password = secrets.token_urlsafe(16)
                    member = User.objects.create_user(
                        email=email,
                        name=email.split("@")[0],
                        password=temp_password,
                        role=role,
                        organization=org,
                        is_email_verified=False,
                    )
                    break
                except IntegrityError:
                    if _attempt == 2:
                        raise ValidationError({"email": ["User already exists."]})
            logger.info(
                "Invited new member %s to org %s",
                email,
                org.id,
                extra={"org_id": str(org.id), "member_email": email},
            )
        except (OperationalError, ProgrammingError) as exc:
            logger.error("DB error in add_org_member: %s", exc, extra={"org_id": str(org.id)})
            raise ValidationError({"detail": "Service unavailable. Try again."})
        else:
            if member.organization_id == org.pk:
                raise ValidationError({"email": ["User is already a member of this organization."]})

            if member.organization_id is not None:
                raise ValidationError({"email": ["User already belongs to another organization."]})

            member.organization = org
            member.role = role
            member.save(update_fields=["organization", "role", "updated_at"])

        try:
            from apps.core.models import AuditLog

            AuditLog.objects.create(
                action="MEMBER_ADDED",
                actor=requesting_user,
                organization=org,
                resource_type="user",
                resource_id=str(member.id),
                changes={"email": email, "role": role},
            )
        except ValidationError:
            raise
        except Exception as exc:
            logger.warning(
                "AuditLog failed add_org_member: %s",
                exc,
                extra={"org_id": str(org.id), "member_id": str(member.id)},
            )

    return member


def remove_org_member(org: Organization, member_id: str, requesting_user) -> None:
    if not org:
        raise ValidationError({"detail": "Organization is required."})

    with transaction.atomic():
        try:
            member = User.objects.select_for_update().get(pk=member_id, organization=org)
        except User.DoesNotExist:
            from rest_framework.exceptions import NotFound

            raise NotFound("Member not found in this organization.")
        except (OperationalError, ProgrammingError) as exc:
            logger.error("DB error in remove_org_member: %s", exc, extra={"org_id": str(org.id)})
            raise ValidationError({"detail": "Service unavailable. Try again."})

        if org.owner_id == member.pk:
            raise ValidationError({"detail": "Cannot remove the organization owner."})

        if str(requesting_user.pk) == str(member.pk):
            raise ValidationError({"detail": "Cannot remove yourself from the organization."})

        member.organization = None
        member.role = "member"
        member.save(update_fields=["organization", "role", "updated_at"])

        try:
            from apps.core.models import AuditLog

            AuditLog.objects.create(
                action="MEMBER_REMOVED",
                actor=requesting_user,
                organization=org,
                resource_type="user",
                resource_id=str(member.id),
                changes={"email": member.email},
            )
        except ValidationError:
            raise
        except Exception as exc:
            logger.warning(
                "AuditLog failed remove_org_member: %s",
                exc,
                extra={"org_id": str(org.id), "member_id": str(member.id)},
            )


def update_org_settings(org: Organization, data: dict, user=None) -> Organization:
    with transaction.atomic():
        org = Organization.objects.select_for_update().get(pk=org.pk)
        for field, value in data.items():
            if field not in _ORG_UPDATE_ALLOWED_FIELDS:
                continue
            setattr(org, field, value)
        changed = [f for f in _ORG_UPDATE_ALLOWED_FIELDS if f in data]
        if changed:
            org.save(update_fields=changed + ["updated_at"])

        try:
            from apps.core.models import AuditLog

            AuditLog.objects.create(
                action="ORG_SETTINGS_UPDATE",
                actor=user,
                organization=org,
                resource_type="organization",
                resource_id=str(org.id),
                changes={"fields_updated": changed},
            )
        except ValidationError:
            raise
        except Exception as exc:
            logger.warning(
                "AuditLog write failed in update_org_settings: %s",
                exc,
                extra={"org_id": str(org.id)},
            )

    return org


@transaction.atomic
def gdpr_erase_user(user, requesting_user=None):
    from apps.core.models import AuditLog

    user_id = str(user.id)

    user.email = f"erased-{user_id[:8]}@deleted.local"
    user.name = "[Deleted User]"
    user.is_active = False
    user.save(update_fields=["email", "name", "is_active", "updated_at"])

    try:
        AuditLog.objects.create(
            organization=user.organization,
            actor=requesting_user or user,
            action="GDPR_ERASE",
            resource_type="User",
            resource_id=user_id,
            changes={"pseudonymized": True},
        )
    except ValidationError:
        raise
    except Exception as exc:
        logger.warning(
            "AuditLog write failed in gdpr_erase_user: %s",
            exc,
            extra={"user_id": user_id},
        )

    logger.info("GDPR erase completed for user %s", user_id, extra={"user_id": user_id})
