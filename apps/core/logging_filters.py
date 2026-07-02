import logging
import re

SENSITIVE_PATTERNS = [
    (re.compile(r"(password\s*[:=]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(token\s*[:=]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(secret\s*[:=]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(authorization\s*[:=]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(x-api-key\s*[:=]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(stripe_secret\s*[:=]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
]


class ScrubSensitiveFilter(logging.Filter):
    def filter(self, record):
        record.msg = self._scrub(str(record.msg))
        record.args = self._scrub_args(record.args)
        return True

    def _scrub(self, text):
        for pattern, replacement in SENSITIVE_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _scrub_args(self, args):
        if not args:
            return args
        if isinstance(args, dict):
            return {k: self._scrub(str(v)) for k, v in args.items()}
        if isinstance(args, (list, tuple)):
            return type(args)(self._scrub(str(a)) for a in args)
        return args


class TraceContextFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "otelTraceID"):
            record.otelTraceID = "-"
        if not hasattr(record, "otelSpanID"):
            record.otelSpanID = "-"
        return True


class TraceIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        trace_id = self._get_trace_id()
        request.trace_id = trace_id
        response = self.get_response(request)
        if trace_id:
            response["X-Trace-ID"] = trace_id
        return response

    @staticmethod
    def _get_trace_id() -> str:
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx.is_valid:
                return format(ctx.trace_id, "032x")
        except (ImportError, AttributeError, RuntimeError):
            return ""
