"""OpenTelemetry tracing configuration.

Supports both self-hosted backends (Jaeger, local Tempo) and managed
services (Grafana Cloud, Datadog, Honeycomb, New Relic, etc.)
via standard OTEL environment variables.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Self

from backend.settings import (
    ENV as _ENV,
)
from backend.settings import (
    OTEL_ENABLED as _OTEL_ENABLED,
)
from backend.settings import (
    OTEL_EXPORTER_OTLP_COMPRESSION as _OTEL_EXPORTER_OTLP_COMPRESSION,
)
from backend.settings import (
    OTEL_EXPORTER_OTLP_ENDPOINT as _OTEL_EXPORTER_OTLP_ENDPOINT,
)
from backend.settings import (
    OTEL_EXPORTER_OTLP_HEADERS as _OTEL_EXPORTER_OTLP_HEADERS,
)
from backend.settings import (
    OTEL_EXPORTER_OTLP_PROTOCOL as _OTEL_EXPORTER_OTLP_PROTOCOL,
)
from backend.settings import (
    OTEL_EXPORTER_OTLP_TIMEOUT as _OTEL_EXPORTER_OTLP_TIMEOUT,
)
from backend.settings import (
    OTEL_RESOURCE_ATTRIBUTES as _OTEL_RESOURCE_ATTRIBUTES,
)
from backend.settings import (
    OTEL_SAMPLER_ARG as _OTEL_SAMPLER_ARG,
)
from backend.settings import (
    OTEL_SAMPLER_TYPE as _OTEL_SAMPLER_TYPE,
)
from backend.settings import (
    OTEL_SERVICE_NAME as _OTEL_SERVICE_NAME,
)
from backend.settings import (
    OTEL_SERVICE_VERSION as _OTEL_SERVICE_VERSION,
)

OTEL_ENABLED = _OTEL_ENABLED
OTEL_EXPORTER_OTLP_PROTOCOL = _OTEL_EXPORTER_OTLP_PROTOCOL
OTEL_EXPORTER_OTLP_ENDPOINT = _OTEL_EXPORTER_OTLP_ENDPOINT
OTEL_EXPORTER_OTLP_HEADERS = _OTEL_EXPORTER_OTLP_HEADERS
OTEL_EXPORTER_OTLP_COMPRESSION = _OTEL_EXPORTER_OTLP_COMPRESSION
OTEL_EXPORTER_OTLP_TIMEOUT = _OTEL_EXPORTER_OTLP_TIMEOUT
OTEL_SAMPLER_TYPE = _OTEL_SAMPLER_TYPE
OTEL_SAMPLER_ARG = _OTEL_SAMPLER_ARG
OTEL_SERVICE_NAME = _OTEL_SERVICE_NAME
OTEL_SERVICE_VERSION = _OTEL_SERVICE_VERSION
OTEL_RESOURCE_ATTRIBUTES = _OTEL_RESOURCE_ATTRIBUTES
ENV = _ENV

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace as _trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter as _OTLPHttpExporter,
    )
    from opentelemetry.instrumentation.fastapi import (
        FastAPIInstrumentor as _FastAPIInstrumentor,
    )
    from opentelemetry.instrumentation.httpx import (
        HTTPXClientInstrumentor as _HTTPXClientInstrumentor,
    )
    from opentelemetry.sdk.resources import Resource as _Resource
    from opentelemetry.sdk.trace import (
        TracerProvider as _TracerProvider,
    )
    from opentelemetry.sdk.trace import (
        sampling as _sampling,
    )
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor as _BatchSpanProcessor,
    )
    from opentelemetry.sdk.trace.export import (
        SimpleSpanProcessor as _SimpleSpanProcessor,
    )

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    _trace = None  # type: ignore[no-redef,assignment]
    _Resource = None  # type: ignore[no-redef,misc,assignment]
    _TracerProvider = None  # type: ignore[no-redef,misc,assignment]
    _sampling = None  # type: ignore[no-redef,assignment]
    _BatchSpanProcessor = None  # type: ignore[no-redef,misc,assignment]
    _SimpleSpanProcessor = None  # type: ignore[no-redef,misc,assignment]
    _OTLPHttpExporter = None  # type: ignore[no-redef,misc,assignment]
    _FastAPIInstrumentor = None  # type: ignore[no-redef,misc,assignment]
    _HTTPXClientInstrumentor = None  # type: ignore[no-redef,misc,assignment]

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as OTLPGrpcExporter,
    )
except ImportError:
    OTLPGrpcExporter = None


def _parse_resource_attributes(raw: str) -> dict[str, str]:
    """Parse OTEL_RESOURCE_ATTRIBUTES (key1=val1,key2=val2) into a dict."""
    attrs: dict[str, str] = {}
    if not raw:
        return attrs
    for pair in raw.split(","):
        if "=" in pair:
            key, val = pair.split("=", 1)
            attrs[key.strip()] = val.strip()
    return attrs


def _create_sampler():
    """Create a sampler based on OTEL_SAMPLER_TYPE and OTEL_SAMPLER_ARG."""
    if not _OTEL_AVAILABLE:
        return None
    sampler_type = OTEL_SAMPLER_TYPE
    sampler_arg = float(OTEL_SAMPLER_ARG)

    samplers = {
        "always_on": _sampling.ALWAYS_ON,
        "always_off": _sampling.ALWAYS_OFF,
        "traceidratio": _sampling.TraceIdRatioBased(sampler_arg),
        "parentbased_traceidratio": _sampling.ParentBased(_sampling.TraceIdRatioBased(sampler_arg)),
        "parentbased_always_on": _sampling.ParentBased(_sampling.ALWAYS_ON),
        "parentbased_always_off": _sampling.ParentBased(_sampling.ALWAYS_OFF),
    }

    return samplers.get(sampler_type, _sampling.ParentBased(_sampling.TraceIdRatioBased(0.1)))


def _create_otlp_exporter():
    """Create an OTLP exporter based on configuration."""
    if not _OTEL_AVAILABLE:
        return None
    if not OTEL_EXPORTER_OTLP_ENDPOINT:
        logger.warning("No OTLP endpoint configured -- traces will not be exported")
        return None

    headers = {}
    if OTEL_EXPORTER_OTLP_HEADERS:
        for pair in OTEL_EXPORTER_OTLP_HEADERS.split(","):
            if "=" in pair:
                key, val = pair.split("=", 1)
                headers[key.strip()] = val.strip()

    common_args = {
        "endpoint": OTEL_EXPORTER_OTLP_ENDPOINT,
        "headers": headers,
        "timeout": OTEL_EXPORTER_OTLP_TIMEOUT,
    }

    if OTEL_EXPORTER_OTLP_PROTOCOL == "grpc":
        try:
            return OTLPGrpcExporter(
                **common_args,
                compression=OTEL_EXPORTER_OTLP_COMPRESSION,
            )
        except Exception as e:
            logger.warning(f"Failed to create gRPC exporter, falling back to HTTP: {e}")

    try:
        return _OTLPHttpExporter(
            **common_args,
            compression=OTEL_EXPORTER_OTLP_COMPRESSION,
        )
    except Exception as e:
        logger.warning(f"Failed to create HTTP exporter: {e}")
        return None


def setup_tracing(app=None):
    """Configure OpenTelemetry tracing."""
    if not OTEL_ENABLED:
        logger.info("OpenTelemetry tracing is disabled")
        return
    if not _OTEL_AVAILABLE:
        logger.warning("OpenTelemetry packages not installed")
        return

    resource_attrs = {
        "service.name": OTEL_SERVICE_NAME,
        "service.version": OTEL_SERVICE_VERSION,
        "deployment.environment": ENV,
    }
    resource_attrs.update(_parse_resource_attributes(OTEL_RESOURCE_ATTRIBUTES))

    resource = _Resource.create(resource_attrs)
    sampler = _create_sampler()
    provider = _TracerProvider(resource=resource, sampler=sampler)

    exporter = _create_otlp_exporter()
    if exporter:
        if ENV == "development":
            provider.add_span_processor(_SimpleSpanProcessor(exporter))
            logger.info("Using SimpleSpanProcessor (development mode)")
        else:
            provider.add_span_processor(
                _BatchSpanProcessor(
                    exporter,
                    max_queue_size=2048,
                    max_export_batch_size=512,
                    schedule_delay_millis=5000,
                )
            )
            logger.info("Using BatchSpanProcessor (production mode)")

    _trace.set_tracer_provider(provider)

    if app:
        try:
            _FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI instrumented for tracing")
        except Exception as e:
            logger.warning(f"Failed to instrument FastAPI: {e}")

    try:
        _HTTPXClientInstrumentor().instrument()
        logger.info("HTTPX instrumented for tracing")
    except Exception as e:
        logger.warning(f"Failed to instrument HTTPX: {e}")

    logger.info(
        "OpenTelemetry tracing configured",
        endpoint=OTEL_EXPORTER_OTLP_ENDPOINT or "none (local only)",
        protocol=OTEL_EXPORTER_OTLP_PROTOCOL,
        sampler=f"{OTEL_SAMPLER_TYPE}({OTEL_SAMPLER_ARG})",
    )


def get_tracer(name: str = __name__) -> object:
    """Return an OpenTelemetry tracer, or a no-op stub if disabled/unavailable.

    Usage::

        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("my_span"):
            ...
    """
    if not OTEL_ENABLED or not _OTEL_AVAILABLE or _trace is None:
        return _NoOpTracer()
    return _trace.get_tracer(name)


class _NoOpTracer:
    """No-op tracer stub used when OpenTelemetry is disabled or unavailable.

    Every method is a no-op that returns self for fluent chaining,
    allowing ``with tracer.start_as_current_span(...)`` to work safely
    without runtime overhead.
    """

    def start_as_current_span(self, name: str, **kwargs: object) -> _NoOpSpan:
        return _NoOpSpan()

    def start_span(self, name: str, **kwargs: object) -> _NoOpSpan:
        return _NoOpSpan()


class _NoOpSpan:
    """No-op span context manager that supports all real Span methods as no-ops."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def set_attribute(self, key: str, value: object) -> None:
        pass

    def set_attributes(self, attributes: dict[str, object]) -> None:
        pass

    def add_event(
        self, name: str, attributes: dict[str, object] | None = None,
        timestamp: int | None = None,
    ) -> None:
        pass

    def record_exception(
        self, exception: BaseException,
        attributes: dict[str, object] | None = None,
        timestamp: int | None = None,
        escaped: bool = False,
    ) -> None:
        pass

    def set_status(self, status: object, description: str | None = None) -> None:
        pass

    def update_name(self, name: str) -> None:
        pass

    def end(self, end_time: int | None = None) -> None:
        pass

    def is_recording(self) -> bool:
        return False

    def get_span_context(self) -> object:
        return None

    def add_link(
        self, context: object, attributes: dict[str, object] | None = None,
    ) -> None:
        pass
