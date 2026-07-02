from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import StandardCursorPagination
from apps.core.permissions import IsAdmin, IsOrgScopedObject, RequiresOrg

from . import services
from .serializers import AlertSerializer, BulkResolveSerializer, ResolveAlertSerializer


class AlertListView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    serializer_class = AlertSerializer
    pagination_class = StandardCursorPagination

    def get(self, request):
        qs = services.list_alerts(request.user.organization, request.query_params)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(AlertSerializer(page, many=True).data)


class AlertDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin, IsOrgScopedObject]
    serializer_class = AlertSerializer

    def get_queryset(self):
        from .models import Alert

        return Alert.objects.filter(
            organization=self.request.user.organization,
            deleted_at__isnull=True,
        ).select_related("scan", "resolved_by", "domain", "domain__organization")

    def get(self, request, pk):
        obj = self.get_object()
        return Response(AlertSerializer(obj).data)

    def patch(self, request, pk):
        self.get_object()
        ser = ResolveAlertSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        alert = services.resolve_alert(
            alert_id=pk,
            org=request.user.organization,
            user=request.user,
            note=ser.validated_data.get("resolved_note", ""),
        )
        return Response(AlertSerializer(alert).data)


class AlertResolveView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin, IsOrgScopedObject]
    serializer_class = ResolveAlertSerializer

    def get_queryset(self):
        from .models import Alert

        return Alert.objects.filter(
            organization=self.request.user.organization,
            deleted_at__isnull=True,
        )

    def post(self, request, pk):
        self.get_object()
        ser = ResolveAlertSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        alert = services.resolve_alert(
            alert_id=pk,
            org=request.user.organization,
            user=request.user,
            note=ser.validated_data.get("resolved_note", ""),
        )
        return Response(AlertSerializer(alert).data)


class AlertBulkResolveView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    serializer_class = BulkResolveSerializer

    def post(self, request):
        ser = BulkResolveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        resolved_count = services.bulk_resolve_alerts(
            org=request.user.organization,
            user=request.user,
            ids=ser.validated_data["ids"],
        )
        return Response({"resolved": resolved_count}, status=status.HTTP_200_OK)
