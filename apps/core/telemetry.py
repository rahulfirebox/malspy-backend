import logging

logger = logging.getLogger(__name__)

_CONFIGURED = False


def configure_opentelemetry(service_name: str, otlp_endpoint: str = "") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource(attributes={SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)

        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
        else:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            exporter = ConsoleSpanExporter()

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        try:
            from opentelemetry.instrumentation.django import DjangoInstrumentor

            DjangoInstrumentor().instrument()
        except ImportError:
            logger.debug("opentelemetry-instrumentation-django not installed; skipping")

        try:
            from opentelemetry.instrumentation.celery import CeleryInstrumentor

            CeleryInstrumentor().instrument()
        except ImportError:
            logger.debug("opentelemetry-instrumentation-celery not installed; skipping")

        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor

            RedisInstrumentor().instrument()
        except ImportError:
            logger.debug("opentelemetry-instrumentation-redis not installed; skipping")

        try:
            from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

            Psycopg2Instrumentor().instrument()
        except ImportError:
            logger.debug("opentelemetry-instrumentation-psycopg2 not installed; skipping")

        try:
            from opentelemetry.instrumentation.logging import LoggingInstrumentor

            LoggingInstrumentor().instrument(set_logging_format=False)
        except ImportError:
            logger.debug("opentelemetry-instrumentation-logging not installed; skipping")

        logger.info("OpenTelemetry configured for service: %s", service_name)

    except ImportError:
        logger.warning(
            "opentelemetry-sdk not installed; tracing disabled. "
            "Add opentelemetry-sdk to requirements to enable."
        )
