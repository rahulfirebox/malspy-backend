from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


class Role:
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    MEMBER = "member"
    OWNER = "owner"
    VIEWER = "viewer"


class Permission:
    DOMAIN_VIEW = "domain:view"
    DOMAIN_CREATE = "domain:create"
    DOMAIN_DELETE = "domain:delete"
    SCAN_VIEW = "scan:view"
    SCAN_TRIGGER = "scan:trigger"
    ALERT_VIEW = "alert:view"
    ALERT_RESOLVE = "alert:resolve"
    BILLING_VIEW = "billing:view"
    BILLING_MANAGE = "billing:manage"
    USER_INVITE = "user:invite"
    USER_MANAGE = "user:manage"
    API_KEY_MANAGE = "api_key:manage"
    REPORT_EXPORT = "report:export"
    SUPERADMIN_MANAGE = "superadmin:manage"


ROLE_PERMISSION_MAP = {
    "admin": [
        Permission.DOMAIN_VIEW,
        Permission.DOMAIN_CREATE,
        Permission.DOMAIN_DELETE,
        Permission.SCAN_VIEW,
        Permission.SCAN_TRIGGER,
        Permission.ALERT_VIEW,
        Permission.ALERT_RESOLVE,
        Permission.BILLING_VIEW,
        Permission.BILLING_MANAGE,
        Permission.USER_INVITE,
        Permission.USER_MANAGE,
        Permission.API_KEY_MANAGE,
        Permission.REPORT_EXPORT,
    ],
    "superadmin": [v for k, v in vars(Permission).items() if not k.startswith("_")],
}


def has_permission(user, permission: str) -> bool:

    role = getattr(user, "role", None)
    if role is None:
        return False
    allowed = ROLE_PERMISSION_MAP.get(role, [])
    return permission in allowed


class RequiresOrg(BasePermission):

    message = "Organization context required."

    def has_permission(self, request, view):
        if not (
            request.user
            and request.user.is_authenticated
            and request.user.organization_id is not None
        ):
            return False
        if not getattr(request.user, "is_email_verified", False):
            self.message = "Email verification required."
            return False
        org = getattr(request.user, "organization", None)
        if org is not None and not org.is_active:
            raise PermissionDenied(
                {"code": "ORG_SUSPENDED", "message": "Your organization has been suspended."}
            )
        return True


class IsAdmin(BasePermission):

    message = "Admin role required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ("owner", "admin", "superadmin")
        )


class IsSuperAdmin(BasePermission):

    message = "Superadmin role required."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.role == Role.SUPERADMIN
        )


class RequiresPermission(BasePermission):

    def __init__(self, permission_name: str) -> None:
        self.permission_name = permission_name

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and has_permission(request.user, self.permission_name)
        )


class IsOrgScopedObject(BasePermission):

    message = "Object not found in your organization."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        if request.user.role == Role.SUPERADMIN:
            return True
        org_id = getattr(obj, "organization_id", None)
        return org_id is not None and str(org_id) == str(request.user.organization_id)


class RequiresActiveSubscription(BasePermission):

    message = "Active subscription required."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        org = getattr(request.user, "organization", None)
        if org is None:
            return False
        sub = getattr(org, "active_subscription", None)
        if sub is None:
            return True
        if sub.status not in ("active", "trialing"):
            raise PermissionDenied(
                {"code": "SUBSCRIPTION_REQUIRED", "message": "Active subscription required."}
            )
        return True
