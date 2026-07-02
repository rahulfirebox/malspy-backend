import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import StandardCursorPagination
from apps.core.permissions import IsAdmin, RequiresOrg

from . import services
from .models import Domain
from .serializers import CreateDomainSerializer, DomainSerializer, UpdateDomainSerializer

logger = logging.getLogger(__name__)


class DomainListView(GenericAPIView):
    serializer_class = DomainSerializer
    pagination_class = StandardCursorPagination

    def get_permissions(self):
        return [IsAuthenticated(), RequiresOrg(), IsAdmin()]

    def get(self, request):
        q = request.query_params.get("q", "").strip() or None
        domain_status = request.query_params.get("status", "").strip() or None
        domains = services.list_domains(request.user.organization, q=q, status=domain_status)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(domains, request)
        if page is not None:
            return paginator.get_paginated_response(DomainSerializer(page, many=True).data)
        return Response({"results": DomainSerializer(domains, many=True).data})

    def post(self, request):
        ser = CreateDomainSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        domain = services.create_domain(
            data=ser.validated_data,
            org=request.user.organization,
            user=request.user,
        )
        return Response(DomainSerializer(domain).data, status=status.HTTP_201_CREATED)


class DomainDetailView(GenericAPIView):
    serializer_class = DomainSerializer

    def get_permissions(self):
        return [IsAuthenticated(), RequiresOrg(), IsAdmin()]

    def get_queryset(self):
        return Domain.objects.filter(
            organization=self.request.user.organization,
            deleted_at__isnull=True,
            is_active=True,
        )

    def get(self, request, pk):
        domain = self.get_object()
        return Response(DomainSerializer(domain).data)

    def patch(self, request, pk):
        domain = self.get_object()
        ser = UpdateDomainSerializer(domain, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        updated = services.update_domain(
            pk, ser.validated_data, request.user.organization, request.user
        )
        return Response(DomainSerializer(updated).data)

    def delete(self, request, pk):
        self.get_object()
        services.delete_domain(pk, request.user.organization, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DomainScanView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    serializer_class = None

    def get_queryset(self):
        return Domain.objects.filter(
            organization=self.request.user.organization,
            deleted_at__isnull=True,
            is_active=True,
        )

    def post(self, request, pk):
        org = request.user.organization
        domain = get_object_or_404(self.get_queryset(), pk=pk)
        from apps.scans.services import create_scan

        try:
            scan = create_scan(
                data={
                    "url": f"https://{domain.domain}",
                    "notify_email": domain.notify_email,
                },
                org=org,
                user=request.user,
            )
        except ValidationError as exc:
            detail = exc.detail
            code = "SCAN_ERROR"
            if isinstance(detail, dict):
                code = detail.get("code", code)
            logger.warning(
                "DomainScanView scan request failed for domain %s: %s",
                pk,
                exc,
                extra={"domain_id": str(pk), "org_id": str(org.id)},
            )
            return Response(
                {"error_code": code, "message": "Scan request failed. Please try again."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response({"scan_id": str(scan.id)}, status=status.HTTP_201_CREATED)
