import logging

import jwt as pyjwt
from django.conf import settings
from django.db import OperationalError
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)


class IsAgentJWT(BasePermission):
    message = "Valid agent token required."

    def has_permission(self, request, view):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        token_str = auth.split(" ", 1)[1]
        try:
            payload = pyjwt.decode(
                token_str,
                settings.AGENT_JWT_SIGNING_KEY,
                algorithms=["HS256"],
            )
            if payload.get("token_type") != "agent_access":
                raise PermissionDenied(
                    {"code": "INVALID_TOKEN_TYPE", "message": "Invalid agent token type."}
                )
            agent_id = payload.get("agent_id")
            if not agent_id:
                return False
            from .models import ServerAgent

            agent = ServerAgent.all_objects.select_related("organization").get(
                pk=agent_id,
                status="active",
                deleted_at__isnull=True,
            )
            org_id_claim = payload.get("org_id")
            if org_id_claim and org_id_claim != str(agent.organization_id):
                logger.warning(
                    "IsAgentJWT: org_id claim %s != agent.organization_id %s",
                    org_id_claim,
                    agent.organization_id,
                    extra={"org_id_claim": org_id_claim, "agent_id": str(agent_id)},
                )
                return False
            request.agent = agent
            request.organization = agent.organization
            return True
        except pyjwt.ExpiredSignatureError:
            logger.warning("IsAgentJWT: token expired", extra={})
            return False
        except pyjwt.InvalidTokenError as e:
            logger.warning("IsAgentJWT: invalid token: %s", e, extra={})
            return False
        except ServerAgent.DoesNotExist:
            return False
        except OperationalError as e:
            logger.error("DB error during agent JWT auth: %s", e, exc_info=True, extra={})
            raise APIException(detail="Service temporarily unavailable.")
        except APIException:
            raise
