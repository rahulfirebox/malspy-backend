from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import StandardCursorPagination
from apps.core.permissions import IsAdmin, IsOrgScopedObject, RequiresOrg

from . import services
from .serializers import ApiKeyCreateSerializer, ApiKeySerializer


class ApiKeyListView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin]
    serializer_class = ApiKeySerializer
    pagination_class = StandardCursorPagination

    def get(self, request):
        qs = services.list_api_keys(request.user.organization)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        if page is not None:
            serializer = ApiKeySerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        return Response(
            {
                "success": True,
                "data": {
                    "results": ApiKeySerializer(qs, many=True).data,
                },
            }
        )

    def post(self, request):
        ser = ApiKeyCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        api_key, raw_key = services.create_api_key(
            data=ser.validated_data,
            org=request.user.organization,
            user=request.user,
        )
        return Response(
            {
                "success": True,
                "data": {
                    "id": str(api_key.id),
                    "name": api_key.name,
                    "key_prefix": api_key.key_prefix,
                    "raw_key": raw_key,
                    "revoked": api_key.revoked,
                    "expires_at": (api_key.expires_at.isoformat() if api_key.expires_at else None),
                    "created_at": api_key.created_at.isoformat(),
                    "warning": "Copy this key now -- it will not be shown again.",
                },
            },
            status=status.HTTP_201_CREATED,
        )


class ApiKeyDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated, RequiresOrg, IsAdmin, IsOrgScopedObject]
    serializer_class = ApiKeySerializer

    def get_queryset(self):
        from .models import ApiKey

        return ApiKey.objects.filter(organization=self.request.user.organization)

    def delete(self, request, pk):
        self.get_object()
        services.revoke_api_key(pk, request.user.organization, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
