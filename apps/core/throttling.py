from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle


class _RateLimitHeaderMixin:

    def throttle_success(self):
        result = super().throttle_success()
        return result

    def allow_request(self, request, view):
        allowed = super().allow_request(request, view)
        if hasattr(request, "_request"):
            num_requests, duration = self.get_rate().split("/")
            num_requests = int(num_requests)
            history = self.cache.get(self.key, [])
            remaining = max(0, num_requests - len(history))
            reset = (
                int(self.duration - (self.timer() - history[-1])) if history else int(self.duration)
            )
            if not hasattr(request, "_rate_limit_headers"):
                request._rate_limit_headers = {}
            request._rate_limit_headers[self.scope] = {
                "X-RateLimit-Limit": str(num_requests),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(max(0, reset)),
            }
        return allowed


class LoginRateThrottle(_RateLimitHeaderMixin, AnonRateThrottle):

    scope = "login"


class RegistrationRateThrottle(AnonRateThrottle):

    scope = "registration"


class PasswordResetThrottle(AnonRateThrottle):

    scope = "password_reset"


class EmailVerifyThrottle(AnonRateThrottle):

    scope = "email_verify"


class PublicScanThrottle(AnonRateThrottle):

    scope = "public_scan"


class SensitiveActionThrottle(UserRateThrottle):

    scope = "sensitive"


class StandardUserThrottle(UserRateThrottle):

    scope = "user"


class ScanStatusUserThrottle(UserRateThrottle):
    scope = "scan_status_user"


class ScanStatusAnonThrottle(AnonRateThrottle):
    scope = "scan_status_anon"


class AgentAuthThrottle(AnonRateThrottle):

    scope = "agent_auth"


class AgentRateThrottle(SimpleRateThrottle):

    scope = "agent"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }
