import logging

from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import StandardCursorPagination
from apps.core.permissions import IsAdmin, IsOrgScopedObject, RequiresOrg
from apps.core.throttling import AgentAuthThrottle, AgentRateThrottle

from . import services
from .permissions import IsAgentJWT
from .serializers import (
    AgentReportSerializer,
    ServerAgentCreateSerializer,
    ServerAgentSerializer,
    ServerScanResultSerializer,
)

logger = logging.getLogger(__name__)


class AgentListView(GenericAPIView):

    pagination_class = StandardCursorPagination
    serializer_class = ServerAgentSerializer

    def get_permissions(self):
        return [IsAuthenticated(), RequiresOrg(), IsAdmin()]

    def get(self, request):

        agents = services.AgentService.list(request.user.organization)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(agents, request)
        if page is not None:
            return paginator.get_paginated_response(ServerAgentSerializer(page, many=True).data)
        return Response(
            {
                "results": ServerAgentSerializer(agents, many=True).data,
                "count": len(agents),
            }
        )

    def post(self, request):
        ser = ServerAgentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        agent, raw_token = services.AgentService.create(
            organization=request.user.organization,
            name=ser.validated_data["name"],
            user=request.user,
            agent_type=ser.validated_data.get("agent_type", "python_script"),
            domain_id=ser.validated_data.get("domain"),
        )
        data = ServerAgentSerializer(agent).data
        data["token"] = raw_token
        return Response(data, status=status.HTTP_201_CREATED)


class AgentDetailView(GenericAPIView):

    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin, IsOrgScopedObject]

    def get_queryset(self):
        from .models import ServerAgent

        return ServerAgent.objects.filter(
            organization=self.request.user.organization,
            deleted_at__isnull=True,
        )

    def delete(self, request, pk):
        from .models import ServerAgent

        try:
            agent = self.get_queryset().get(pk=pk)
        except ServerAgent.DoesNotExist:
            return Response(
                {"error_code": "NOT_FOUND", "message": "Agent not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        self.check_object_permissions(request, agent)
        services.AgentService.revoke(request.user.organization, agent.pk, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AgentScanListView(GenericAPIView):

    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    pagination_class = StandardCursorPagination
    serializer_class = ServerScanResultSerializer

    def get_queryset(self):
        from .models import ServerScanResult

        agent_pk = self.kwargs["pk"]
        return ServerScanResult.objects.filter(
            agent__pk=agent_pk,
            agent__organization=self.request.user.organization,
            agent__deleted_at__isnull=True,
        ).order_by("-created_at")

    def get(self, request, pk):
        from .models import ServerAgent

        if not ServerAgent.objects.filter(
            pk=pk, organization=request.user.organization, deleted_at__isnull=True
        ).exists():
            return Response(
                {"error_code": "NOT_FOUND", "message": "Agent not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        scans = services.AgentService.list_scans(request.user.organization, pk)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(scans, request)
        if page is not None:
            return paginator.get_paginated_response(
                ServerScanResultSerializer(page, many=True).data
            )
        return Response(ServerScanResultSerializer(scans, many=True).data)


class AgentAuthView(GenericAPIView):

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AgentAuthThrottle]

    def post(self, request):
        raw_token = request.data.get("token", "")
        if not raw_token:
            return Response(
                {"error_code": "INVALID_TOKEN", "message": "Token required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            auth_data = services.AgentService.authenticate(raw_token)
        except PermissionDenied:
            return Response(
                {"error_code": "INVALID_TOKEN", "message": "Invalid or revoked token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(auth_data)


class AgentReportView(GenericAPIView):

    permission_classes = [IsAgentJWT]
    throttle_classes = [AgentRateThrottle]

    def post(self, request):
        ser = AgentReportSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result, alerts_created = services.AgentService.process_report(
            agent=request.agent,
            findings=ser.validated_data["findings"],
            files_scanned=ser.validated_data["files_scanned"],
            scan_duration_ms=ser.validated_data["scan_duration_ms"],
            agent_version=ser.validated_data.get("agent_version", "1.0.0"),
        )
        return Response(
            {
                "server_scan_result_id": str(result.id),
                "alerts_created": alerts_created,
                "status": "completed",
            },
            status=status.HTTP_201_CREATED,
        )


class AgentSignaturesView(GenericAPIView):

    permission_classes = [IsAgentJWT]
    throttle_classes = [AgentRateThrottle]

    def get(self, request):
        sigs = services.AgentService.get_active_signatures()
        return Response({"signatures": sigs})
