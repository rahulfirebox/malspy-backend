import logging

from django.http import HttpResponse
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import StandardCursorPagination
from apps.core.permissions import IsAdmin, IsOrgScopedObject, RequiresOrg
from apps.core.throttling import (
    PublicScanThrottle,
    ScanStatusAnonThrottle,
    ScanStatusUserThrottle,
    StandardUserThrottle,
)

from . import services
from .serializers import (
    CreateScanSerializer,
    PublicScanSerializer,
    ScanDetailSerializer,
    ScanReadSerializer,
    ScanStatusSerializer,
)

logger = logging.getLogger(__name__)


class PublicScanView(GenericAPIView):

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicScanThrottle]
    serializer_class = PublicScanSerializer

    def post(self, request):
        ser = PublicScanSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        scan = services.create_public_scan(url=ser.validated_data["url"])

        if scan.status == "completed":
            return Response(ScanDetailSerializer(scan).data, status=status.HTTP_200_OK)

        return Response(
            {
                "scan_id": str(scan.id),
                "status": scan.status,
                "domain": scan.domain,
                "created_at": scan.created_at.isoformat(),
                "estimated_duration_seconds": 30,
            },
            status=status.HTTP_201_CREATED,
        )


class ScanStatusView(GenericAPIView):

    permission_classes = [AllowAny]
    authentication_classes = []
    pagination_class = None
    throttle_classes = [ScanStatusUserThrottle, ScanStatusAnonThrottle]
    serializer_class = ScanStatusSerializer

    def get(self, request, pk):
        try:
            scan = services.get_scan_status(pk, user=request.user)
            if scan is None:
                return Response(
                    {"error_code": "NOT_FOUND", "message": "Scan not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(ScanStatusSerializer(scan).data)
        except Exception as e:
            logger.error("ScanStatusView error: %s", e, extra={"scan_pk": str(pk)})
            return Response(
                {"error_code": "SERVER_ERROR", "message": "An error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PublicScanDetailView(GenericAPIView):

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicScanThrottle]
    pagination_class = None
    serializer_class = ScanDetailSerializer

    def get(self, request, pk):
        scan = services.get_public_scan_detail(pk)
        if scan is None:
            return Response(
                {"error_code": "NOT_FOUND", "message": "Scan not found or not yet completed."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ScanDetailSerializer(scan).data)


class ScanListView(GenericAPIView):

    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    throttle_classes = [StandardUserThrottle]
    serializer_class = ScanReadSerializer
    pagination_class = StandardCursorPagination

    def get(self, request):
        qs = services.list_scans(request.user.organization, request.query_params)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            ser = ScanReadSerializer(page, many=True)
            return paginator.get_paginated_response(ser.data)
        return Response({"results": ScanReadSerializer(qs, many=True).data})

    def get_permissions(self):
        return [IsAuthenticated(), RequiresOrg(), IsAdmin()]

    def post(self, request):
        ser = CreateScanSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        scan = services.create_scan(
            data=ser.validated_data,
            org=request.user.organization,
            user=request.user,
        )
        resp_status = status.HTTP_200_OK if scan.was_cached else status.HTTP_201_CREATED
        return Response(ScanReadSerializer(scan).data, status=resp_status)


class ScanDetailView(GenericAPIView):

    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin, IsOrgScopedObject]
    serializer_class = ScanDetailSerializer

    def get_queryset(self):
        from .models import Scan

        return Scan.objects.filter(
            organization=self.request.user.organization,
            deleted_at__isnull=True,
            is_active=True,
        ).select_related("created_by", "organization")

    def get(self, request, pk):
        scan = self.get_object()
        return Response(ScanDetailSerializer(scan).data)

    def delete(self, request, pk):
        self.get_object()
        services.delete_scan(pk, request.user.organization, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ScanRescanView(GenericAPIView):

    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin, IsOrgScopedObject]
    serializer_class = ScanReadSerializer

    def get_queryset(self):
        from .models import Scan

        return Scan.objects.filter(
            organization=self.request.user.organization,
            deleted_at__isnull=True,
            is_active=True,
        ).select_related("created_by", "organization")

    def post(self, request, pk):
        self.get_object()
        new_scan = services.rescan(pk, request.user.organization, request.user)
        return Response(
            {
                "id": str(new_scan.id),
                "parent_scan_id": str(new_scan.parent_scan_id),
                "status": new_scan.status,
                "domain": new_scan.domain,
            },
            status=status.HTTP_201_CREATED,
        )


class DashboardAnalyticsView(GenericAPIView):

    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]

    def get(self, request):
        org = request.user.organization
        try:
            data = services.get_dashboard_analytics(org)
            return Response(data)
        except Exception as exc:
            logger.error(
                "DashboardAnalyticsView error: %s",
                exc,
                exc_info=True,
                extra={"org_id": str(org.id)},
            )
            return Response(
                {"error_code": "SERVER_ERROR", "message": "Failed to load analytics."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ScanPDFView(GenericAPIView):

    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin, IsOrgScopedObject]
    serializer_class = None

    def get_queryset(self):
        from .models import Scan

        return Scan.objects.filter(
            organization=self.request.user.organization,
            deleted_at__isnull=True,
            is_active=True,
        )

    def get(self, request, pk):
        scan = self.get_object()
        services.check_plan_feature(request.user.organization, "pdf_report")

        if scan.status != "completed":
            return Response(
                {"error_code": "VALIDATION_ERROR", "message": "Scan not yet completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .tasks import generate_pdf_report

        pdf_bytes = generate_pdf_report(pk)
        if not pdf_bytes:
            return Response(
                {"error_code": "SERVER_ERROR", "message": "Failed to generate PDF."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="scan-{scan.domain}-report.pdf"'
        return response
