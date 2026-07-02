import logging

from django.db.models import Count, Q
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import StandardPageNumberPagination
from apps.core.permissions import IsSuperAdmin, has_permission

logger = logging.getLogger(__name__)


class SuperadminOrgListView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    pagination_class = StandardPageNumberPagination
    serializer_class = None

    def get(self, request):
        from apps.accounts.models import Organization

        qs = Organization.objects.select_related("plan", "owner").order_by("-created_at")
        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        page = self.paginate_queryset(qs)
        data = [
            {
                "id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "is_active": org.is_active,
                "plan": org.plan.slug if org.plan else None,
                "scan_quota_used": org.scan_quota_used,
                "owner_email": org.owner.email if org.owner else None,
                "created_at": org.created_at.isoformat(),
            }
            for org in page
        ]
        logger.info(
            "Superadmin org list",
            extra={"user_id": str(request.user.id), "count": len(data)},
        )
        return self.get_paginated_response(data)


class SuperadminOrgDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = None

    def get(self, request, pk):
        from apps.accounts.models import Organization

        try:
            org = Organization.objects.select_related("plan", "owner").get(pk=pk)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
        data = {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "is_active": org.is_active,
            "plan": org.plan.slug if org.plan else None,
            "scan_quota_used": org.scan_quota_used,
            "quota_reset_at": (org.quota_reset_at.isoformat() if org.quota_reset_at else None),
            "owner_email": org.owner.email if org.owner else None,
            "created_at": org.created_at.isoformat(),
            "updated_at": org.updated_at.isoformat(),
        }
        return Response(data)

    def patch(self, request, pk):
        from apps.accounts.models import Organization

        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
        allowed_fields = {"is_active", "name"}
        update_fields = []
        for field in allowed_fields:
            if field in request.data:
                setattr(org, field, request.data[field])
                update_fields.append(field)
        if update_fields:
            update_fields.append("updated_at")
            org.save(update_fields=update_fields)
        try:
            from apps.core.models import AuditLog

            AuditLog.objects.create(
                organization=org,
                actor=request.user,
                action="SUPERADMIN_ORG_PATCH",
                resource_type="Organization",
                resource_id=str(org.id),
                changes={"fields_updated": update_fields, "target_org_id": str(pk)},
            )
        except Exception as audit_exc:
            logger.warning(
                "AuditLog failed for superadmin org patch: %s",
                audit_exc,
                extra={"user_id": str(request.user.id), "org_id": str(org.id)},
            )
        logger.info(
            "Superadmin org patch",
            extra={"user_id": str(request.user.id), "org_id": str(org.id)},
        )
        return Response({"id": str(org.id), "is_active": org.is_active, "name": org.name})


class SuperadminUserListView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    pagination_class = StandardPageNumberPagination
    serializer_class = None

    def get(self, request):
        from apps.accounts.models import User

        qs = User.objects.select_related("organization").order_by("-created_at")
        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(name__icontains=q))
        page = self.paginate_queryset(qs)
        data = [
            {
                "id": str(u.id),
                "email": u.email,
                "name": u.name,
                "role": u.role,
                "is_active": u.is_active,
                "is_email_verified": u.is_email_verified,
                "organization": str(u.organization_id) if u.organization_id else None,
                "org_name": u.organization.name if u.organization else None,
                "created_at": u.created_at.isoformat(),
            }
            for u in page
        ]
        logger.info(
            "Superadmin user list",
            extra={"user_id": str(request.user.id), "count": len(data)},
        )
        return self.get_paginated_response(data)


class SuperadminUserDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = None

    def get(self, request, pk):
        from apps.accounts.models import User

        try:
            u = User.objects.select_related("organization").get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        data = {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "is_active": u.is_active,
            "is_email_verified": u.is_email_verified,
            "organization": str(u.organization_id) if u.organization_id else None,
            "org_name": u.organization.name if u.organization else None,
            "created_at": u.created_at.isoformat(),
            "updated_at": u.updated_at.isoformat(),
        }
        return Response(data)

    def patch(self, request, pk):
        from apps.accounts.models import User

        try:
            u = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        if has_permission(u, "superadmin:manage") and request.data.get("is_active") is False:
            raise ValidationError({"detail": "Cannot deactivate a superadmin account."})
        allowed_fields = {"is_active", "role"}
        update_fields = []
        for field in allowed_fields:
            if field in request.data:
                setattr(u, field, request.data[field])
                update_fields.append(field)
        if update_fields:
            update_fields.append("updated_at")
            u.save(update_fields=update_fields)
        try:
            from apps.core.models import AuditLog

            AuditLog.objects.create(
                organization=u.organization,
                actor=request.user,
                action="SUPERADMIN_USER_PATCH",
                resource_type="User",
                resource_id=str(u.id),
                changes={
                    "fields_updated": update_fields,
                    "target_user_id": str(pk),
                    "target_org_id": (str(u.organization_id) if u.organization_id else None),
                },
            )
        except Exception as audit_exc:
            logger.warning(
                "AuditLog failed for superadmin user patch: %s",
                audit_exc,
                extra={"user_id": str(request.user.id), "target_id": str(u.id)},
            )
        logger.info(
            "Superadmin user patch",
            extra={"user_id": str(request.user.id), "target_id": str(u.id)},
        )
        return Response({"id": str(u.id), "is_active": u.is_active, "role": u.role})


class SuperadminPlanListView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    pagination_class = StandardPageNumberPagination
    serializer_class = None

    def get(self, request):
        from apps.billing.models import Plan

        qs = Plan.objects.order_by("price_monthly")
        page = self.paginate_queryset(qs)
        data = [
            {
                "id": str(p.id),
                "slug": p.slug,
                "name": p.name,
                "price_monthly": str(p.price_monthly),
                "price_yearly": str(p.price_yearly),
                "scan_quota": p.scan_quota,
                "domain_quota": p.domain_quota,
                "is_active": p.is_active,
            }
            for p in page
        ]
        return self.get_paginated_response(data)


class SuperadminStatsView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = None

    def get(self, request):
        from apps.accounts.models import Organization, User

        user_stats = User.objects.aggregate(
            total_users=Count("id"),
            active_users=Count("id", filter=Q(is_active=True)),
            verified_users=Count("id", filter=Q(is_email_verified=True)),
        )
        org_stats = Organization.objects.aggregate(
            total_orgs=Count("id"),
            active_orgs=Count("id", filter=Q(is_active=True)),
        )
        plan_counts = (
            Organization.objects.filter(plan__isnull=False)
            .values("plan__slug")
            .annotate(count=Count("id", distinct=True))
        )
        data = {
            **user_stats,
            **org_stats,
            "plan_distribution": {row["plan__slug"]: row["count"] for row in plan_counts},
        }
        logger.info("Superadmin stats", extra={"user_id": str(request.user.id)})
        return Response(data)


class SuperadminRefundListView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    pagination_class = StandardPageNumberPagination
    serializer_class = None

    def get(self, request):
        from apps.billing.models import Payment

        qs = (
            Payment.objects.filter(status="completed")
            .select_related("organization")
            .order_by("-created_at")
        )
        org_id = request.query_params.get("org_id")
        if org_id:
            qs = qs.filter(organization_id=org_id)
        page = self.paginate_queryset(qs)
        data = [
            {
                "id": str(p.pk),
                "order_id": p.cashfree_order_id,
                "amount": str(p.amount),
                "total_refunded": str(p.total_refunded),
                "currency": p.currency,
                "status": p.status,
                "organization_id": str(p.organization_id),
                "organization_name": p.organization.name if p.organization else "",
                "created_at": p.created_at.isoformat(),
            }
            for p in (page if page is not None else qs[:100])
        ]
        if page is not None:
            return self.get_paginated_response(data)
        return Response({"results": data})


class SuperadminRefundInitiateView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = None

    def post(self, request):
        from apps.billing.cashfree_service import RefundService
        from apps.billing.models import Payment

        payment_id = request.data.get("payment_id", "")
        amount = request.data.get("amount", "")
        reason = request.data.get("reason", "")
        org_id = request.data.get("org_id", "")
        if not payment_id or not amount or not org_id:
            return Response(
                {"detail": "payment_id, amount, and org_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            payment = Payment.objects.get(pk=payment_id, organization_id=org_id)
        except Payment.DoesNotExist:
            return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
        result = RefundService.initiate_refund(
            organization=payment.organization,
            payment_id=payment_id,
            amount=amount,
            reason=reason,
            admin_user=request.user,
        )
        logger.info(
            "Superadmin refund initiated",
            extra={"user_id": str(request.user.id), "payment_id": payment_id},
        )
        return Response(result)


class SuperadminSignatureListView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    pagination_class = StandardPageNumberPagination
    serializer_class = None

    def get(self, request):
        from apps.scans.models import MalwareSignature

        qs = MalwareSignature.objects.all().order_by("signature_id")
        layer = request.query_params.get("layer", "").strip()
        severity = request.query_params.get("severity", "").strip()
        q = request.query_params.get("q", "").strip()
        if layer:
            qs = qs.filter(layer=layer)
        if severity:
            qs = qs.filter(severity=severity)
        if q:
            qs = qs.filter(name__icontains=q)

        page = self.paginate_queryset(qs)
        if page is None:
            page = qs
        data = [
            {
                "id": str(sig.id),
                "signature_id": sig.signature_id,
                "name": sig.name,
                "layer": sig.layer,
                "pattern": sig.pattern,
                "severity": sig.severity,
                "type": sig.type,
                "description": sig.description,
                "is_active": sig.is_active,
                "auto_updated": sig.auto_updated,
                "created_at": sig.created_at.isoformat(),
                "updated_at": sig.updated_at.isoformat(),
            }
            for sig in page
        ]
        return self.get_paginated_response(data)

    def post(self, request):
        from apps.scans.models import MalwareSignature

        required = ("signature_id", "name", "layer", "pattern", "severity", "type")
        for field in required:
            if not request.data.get(field):
                return Response(
                    {"detail": f"'{field}' is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            sig = MalwareSignature.objects.create(
                signature_id=request.data["signature_id"],
                name=request.data["name"],
                layer=request.data["layer"],
                pattern=request.data["pattern"],
                severity=request.data["severity"],
                type=request.data["type"],
                description=request.data.get("description", ""),
                is_active=request.data.get("is_active", True),
            )
        except Exception:
            logger.exception("Failed to create signature", extra={"user_id": str(request.user.id)})
            return Response(
                {"detail": "Failed to create signature. Check field values and try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Superadmin created signature",
            extra={"user_id": str(request.user.id), "signature_id": sig.signature_id},
        )
        return Response(
            {
                "id": str(sig.id),
                "signature_id": sig.signature_id,
                "name": sig.name,
                "layer": sig.layer,
                "pattern": sig.pattern,
                "severity": sig.severity,
                "type": sig.type,
                "description": sig.description,
                "is_active": sig.is_active,
                "auto_updated": sig.auto_updated,
                "created_at": sig.created_at.isoformat(),
                "updated_at": sig.updated_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class SuperadminSignatureDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = None

    def patch(self, request, pk):
        from apps.scans.models import MalwareSignature

        try:
            sig = MalwareSignature.objects.get(pk=pk)
        except MalwareSignature.DoesNotExist:
            return Response({"detail": "Signature not found."}, status=status.HTTP_404_NOT_FOUND)

        allowed = {"is_active", "name", "severity"}
        update_fields = []
        for field in allowed:
            if field in request.data:
                setattr(sig, field, request.data[field])
                update_fields.append(field)

        if update_fields:
            update_fields.append("updated_at")
            sig.save(update_fields=update_fields)

        logger.info(
            "Superadmin patched signature",
            extra={"user_id": str(request.user.id), "sig_id": str(pk)},
        )
        return Response(
            {
                "id": str(sig.id),
                "signature_id": sig.signature_id,
                "name": sig.name,
                "layer": sig.layer,
                "pattern": sig.pattern,
                "severity": sig.severity,
                "type": sig.type,
                "description": sig.description,
                "is_active": sig.is_active,
                "auto_updated": sig.auto_updated,
                "created_at": sig.created_at.isoformat(),
                "updated_at": sig.updated_at.isoformat(),
            }
        )

    def delete(self, request, pk):
        from apps.scans.models import MalwareSignature

        try:
            sig = MalwareSignature.objects.get(pk=pk)
        except MalwareSignature.DoesNotExist:
            return Response({"detail": "Signature not found."}, status=status.HTTP_404_NOT_FOUND)

        sig.delete()
        logger.info(
            "Superadmin deleted signature",
            extra={"user_id": str(request.user.id), "sig_id": str(pk)},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
