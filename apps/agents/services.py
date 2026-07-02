import hashlib
import logging
import secrets
from datetime import timedelta

import jwt as pyjwt
from django.conf import settings
from django.db import IntegrityError, OperationalError, ProgrammingError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.core.models import AuditLog

from .models import ServerAgent, ServerScanResult

logger = logging.getLogger(__name__)

_AGENT_VALID_TRANSITIONS = {
    "inactive": {"active", "revoked"},
    "active": {"inactive", "revoked"},
    "revoked": set(),
}
_AGENT_TERMINAL_STATES = {"revoked"}


def _transition_agent_status(agent, new_status):
    allowed = _AGENT_VALID_TRANSITIONS.get(agent.status, set())
    if new_status not in allowed:
        raise ValidationError(
            {"detail": f"Cannot transition agent from '{agent.status}' to '{new_status}'."}
        )
    agent.status = new_status


class AgentService:

    @staticmethod
    def list(organization):
        try:
            return (
                ServerAgent.objects.filter(
                    organization=organization,
                )
                .select_related("domain", "created_by", "organization")
                .order_by("-created_at")
            )
        except (OperationalError, ProgrammingError) as e:
            logger.error(
                "AgentService.list DB error: %s",
                e,
                extra={"org_id": str(organization.id) if organization else "unknown"},
            )
            raise ValidationError({"detail": "Database temporarily unavailable."})
        except ValidationError:
            raise
        except Exception as e:
            logger.error(
                "AgentService.list unexpected error: %s",
                e,
                exc_info=True,
                extra={"org_id": str(organization.id) if organization else "unknown"},
            )
            raise

    @staticmethod
    @transaction.atomic
    def create(organization, name, user=None, agent_type="python_script", domain_id=None):
        if organization is None:
            raise ValidationError({"detail": "Organization context required."})
        from apps.accounts.models import Organization

        org_locked = Organization.objects.select_for_update().get(pk=organization.pk)
        plan = getattr(org_locked, "plan", None)
        if not plan or plan.agent_quota == 0:
            raise ValidationError(
                {
                    "code": "PLAN_REQUIRED",
                    "detail": "Pro plan required for server agents.",
                }
            )
        if plan.agent_quota != -1:
            current_count = ServerAgent.objects.filter(
                organization=org_locked, deleted_at__isnull=True, revoked=False
            ).count()
            if current_count >= plan.agent_quota:
                raise ValidationError(
                    {
                        "code": "AGENT_QUOTA_EXCEEDED",
                        "detail": f"Agent quota limit of {plan.agent_quota} reached.",
                    }
                )
        if ServerAgent.objects.filter(organization=org_locked, name=name).exists():
            raise ValidationError({"detail": "An active agent with this name already exists."})
        raw_token, token_hash, prefix = ServerAgent.generate_token()
        domain = None
        if domain_id:
            from apps.domains.models import Domain

            try:
                domain = Domain.objects.get(id=domain_id, organization=organization)
            except Domain.DoesNotExist:
                raise NotFound("Domain not found.")
        try:
            agent = ServerAgent.objects.create(
                organization=organization,
                name=name,
                agent_type=agent_type,
                token_hash=token_hash,
                token_prefix=prefix,
                domain=domain,
                created_by=user,
            )
        except IntegrityError:
            raise ValidationError({"name": "Agent with this name already exists."})
        try:
            AuditLog.objects.create(
                organization=organization,
                actor=user,
                action="AGENT_TOKEN_ISSUED",
                resource_type="server_agent",
                resource_id=str(agent.id),
                changes={
                    "agent_id": str(agent.id),
                    "organization_id": str(organization.id),
                },
            )
        except ValidationError:
            raise
        except Exception as audit_exc:
            logger.error(
                "AuditLog write failed for agent create %s: %s",
                agent.id,
                audit_exc,
                extra={"agent_id": str(agent.id), "org_id": str(organization.id)},
            )
        return agent, raw_token

    @staticmethod
    @transaction.atomic
    def revoke(organization, agent_id, user=None):
        try:
            agent = ServerAgent.objects.select_for_update().get(
                pk=agent_id, organization=organization, deleted_at__isnull=True
            )
        except ServerAgent.DoesNotExist:
            raise NotFound("Agent not found.")
        if agent.status == "revoked":
            raise ValidationError({"detail": "Agent is already revoked."})
        _transition_agent_status(agent, "revoked")
        agent.deleted_at = timezone.now()
        agent.token_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        agent.save(update_fields=["status", "token_hash", "deleted_at", "updated_at"])
        try:
            AuditLog.objects.create(
                organization=organization,
                actor=user,
                action="AGENT_TOKEN_REVOKED",
                resource_type="server_agent",
                resource_id=str(agent.id),
                changes={"agent_id": str(agent.id)},
            )
        except ValidationError:
            raise
        except Exception as audit_exc:
            logger.error(
                "AuditLog write failed for agent revoke %s: %s",
                agent.id,
                audit_exc,
                extra={"agent_id": str(agent.id), "org_id": str(organization.id)},
            )

    @staticmethod
    def authenticate(raw_token, agent_version=None):

        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        try:
            agent = ServerAgent.all_objects.select_related(
                "organization", "organization__plan"
            ).get(
                token_hash=token_hash,
                deleted_at__isnull=True,
                status__in=["active", "inactive"],
            )
        except ServerAgent.DoesNotExist:
            raise PermissionDenied("Invalid agent token.")
        org = agent.organization
        if not org.is_active:
            raise PermissionDenied("Organization is suspended.")
        plan = getattr(org, "plan", None)
        if not plan or not getattr(plan, "server_side_scan", False):
            raise PermissionDenied("Plan does not support server agents.")
        now = timezone.now()
        payload = {
            "agent_id": str(agent.id),
            "org_id": str(agent.organization_id),
            "token_type": "agent_access",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
        }
        raw_jwt = pyjwt.encode(payload, settings.AGENT_JWT_SIGNING_KEY, algorithm="HS256")
        if isinstance(raw_jwt, bytes):
            raw_jwt = raw_jwt.decode("utf-8", errors="replace")
        with transaction.atomic():
            agent = ServerAgent.all_objects.select_for_update().get(pk=agent.pk)
            agent.refresh_from_db()
            agent.last_seen_at = now
            _transition_agent_status(agent, "active")
            update_fields = ["last_seen_at", "status", "updated_at"]
            if agent_version:
                agent.agent_version = agent_version
                update_fields.append("agent_version")
            agent.save(update_fields=update_fields)
        try:
            with transaction.atomic():
                AuditLog.objects.create(
                    organization=agent.organization,
                    actor=None,
                    action="agent_authenticated",
                    resource_type="server_agent",
                    resource_id=str(agent.pk),
                    changes={"agent_version": agent_version},
                )
        except ValidationError:
            raise
        except Exception as audit_exc:
            logger.error(
                "AuditLog write failed for agent auth %s: %s",
                agent.pk,
                audit_exc,
                extra={"agent_id": str(agent.pk)},
            )
        return {
            "access": raw_jwt,
            "agent_id": str(agent.id),
            "organization_id": str(agent.organization_id),
        }

    @staticmethod
    def process_report(agent, findings, files_scanned, scan_duration_ms, agent_version="1.0.0"):
        malware_found = len(findings) > 0
        files_infected = len(findings)
        try:
            with transaction.atomic():
                agent = ServerAgent.all_objects.select_for_update().get(pk=agent.pk)
                agent.refresh_from_db()
                result = ServerScanResult.objects.create(
                    agent=agent,
                    organization=agent.organization,
                    files_scanned=files_scanned,
                    files_infected=files_infected,
                    findings=findings,
                    scan_duration_ms=scan_duration_ms,
                    malware_found=malware_found,
                    agent_version=agent_version,
                )
                now = timezone.now()
                agent.last_seen_at = now
                agent.last_scan_at = now
                _transition_agent_status(agent, "active")
                update_fields = ["last_seen_at", "last_scan_at", "status", "updated_at"]
                if agent_version:
                    agent.agent_version = agent_version
                    update_fields.append("agent_version")
                agent.save(update_fields=update_fields)
        except (OperationalError, ProgrammingError) as e:
            logger.error(
                "AgentService.process_report DB error for agent %s: %s",
                agent.pk,
                e,
                extra={"agent_id": str(agent.pk)},
            )
            raise
        except ValidationError:
            raise
        except Exception as e:
            logger.error(
                "AgentService.process_report unexpected error for agent %s: %s",
                agent.pk,
                e,
                exc_info=True,
                extra={"agent_id": str(agent.pk)},
            )
            raise
        alerts_created = 0
        if malware_found:
            from apps.alerts.services import generate_agent_alerts

            alerts_created = generate_agent_alerts(agent, result) or 0
        try:
            with transaction.atomic():
                AuditLog.objects.create(
                    organization=agent.organization,
                    actor=None,
                    action="agent_report_processed",
                    resource_type="server_agent",
                    resource_id=str(agent.pk),
                    changes={
                        "scan_result_id": str(result.id),
                        "files_scanned": files_scanned,
                        "files_infected": files_infected,
                        "malware_found": malware_found,
                        "alerts_created": alerts_created,
                    },
                )
        except ValidationError:
            raise
        except Exception as audit_exc:
            logger.error(
                "AuditLog write failed for agent report %s: %s",
                agent.pk,
                audit_exc,
                extra={"agent_id": str(agent.pk)},
            )
        return result, alerts_created

    @staticmethod
    def list_scans(organization, agent_id):
        try:
            agent = ServerAgent.objects.get(pk=agent_id, organization=organization)
        except ServerAgent.DoesNotExist:
            raise NotFound("Agent not found.")
        try:
            return (
                ServerScanResult.objects.filter(
                    agent=agent,
                )
                .select_related("agent", "organization")
                .order_by("-created_at")
            )
        except (OperationalError, ProgrammingError) as e:
            logger.error(
                "AgentService.list_scans DB error: %s",
                e,
                extra={
                    "agent_id": str(agent_id),
                    "org_id": str(organization.id) if organization else "unknown",
                },
            )
            raise ValidationError({"detail": "Database temporarily unavailable."})
        except ValidationError:
            raise
        except Exception as e:
            logger.error(
                "AgentService.list_scans unexpected error: %s",
                e,
                exc_info=True,
                extra={
                    "agent_id": str(agent_id),
                    "org_id": str(organization.id) if organization else "unknown",
                },
            )
            raise ValidationError({"detail": "An unexpected error occurred."})

    @staticmethod
    def get_active_signatures():
        from django.core.cache import cache

        from apps.scans.models import MalwareSignature

        cache_key = "active_malware_signatures_server"
        lock_key = f"{cache_key}:lock"

        data = cache.get(cache_key)
        if data is not None:
            return data

        if cache.add(lock_key, 1, timeout=30):
            try:

                data = list(
                    MalwareSignature.objects.filter(is_active=True, layer="server")
                    .order_by("-updated_at")
                    .values("signature_id", "pattern", "type", "severity", "name")[:500]
                )

                cache.set(cache_key, data, timeout=300)
            finally:
                cache.delete(lock_key)
        else:
            data = cache.get(cache_key) or []

        return data
