import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Q


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True)
    owner = models.ForeignKey(
        "User",
        on_delete=models.PROTECT,
        related_name="owned_orgs",
        null=True,
        blank=True,
    )
    plan = models.ForeignKey(
        "billing.Plan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizations",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    scan_quota_used = models.IntegerField(default=0)
    quota_reset_at = models.DateTimeField(null=True, blank=True, db_index=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True, default="")
    stripe_subscription_id = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "organizations"
        constraints = [
            models.CheckConstraint(
                check=Q(scan_quota_used__gte=0),
                name="check_org_scan_quota_used_non_negative",
            ),
        ]

    def __str__(self):
        return self.name


_ALLOWED_EXTRA_FIELDS = frozenset(
    {
        "role",
        "is_staff",
        "is_superuser",
        "organization",
        "organization_id",
        "is_active",
        "is_email_verified",
    }
)


class UserManager(BaseUserManager):
    def create_user(self, email, name, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        extra_fields = {k: v for k, v in extra_fields.items() if k in _ALLOWED_EXTRA_FIELDS}
        email = self.normalize_email(email).lower().strip()
        user = self.model(email=email, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None, **extra_fields):
        extra_fields.setdefault("role", "superadmin")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_email_verified", True)
        return self.create_user(email, name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=200)
    role = models.CharField(
        max_length=20,
        choices=[
            ("owner", "Owner"),
            ("admin", "Admin"),
            ("member", "Member"),
            ("viewer", "Viewer"),
            ("superadmin", "Superadmin"),
        ],
        default="admin",
        db_index=True,
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    notify_email = models.BooleanField(default=True)
    timezone = models.CharField(max_length=50, default="UTC")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["organization", "role"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(role__in=["owner", "admin", "member", "viewer", "superadmin"]),
                name="user_role_valid",
            ),
        ]

    def __str__(self):
        return self.email


class PasswordResetToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reset_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    bound_email = models.EmailField(max_length=254, default="")
    purpose = models.CharField(
        max_length=30,
        choices=[
            ("password_reset", "Password Reset"),
            ("email_verify", "Email Verify"),
        ],
        default="password_reset",
        db_index=True,
    )
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "password_reset_tokens"
        constraints = [
            models.CheckConstraint(
                check=models.Q(purpose__in=["password_reset", "email_verify"]),
                name="passwordresettoken_purpose_valid",
            ),
        ]
