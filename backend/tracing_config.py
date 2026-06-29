"""
OpenTelemetry tracing configuration.

Supports both self-hosted backends (Jaeger, local Tempo) and managed
services (Grafana Cloud, Datadog, Honeycomb, New Relic, etc.)
via standard OTEL environment variables.
"""

import os
import logging
from typing import Optional

OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
OTEL_EXPORTER_OTLP_PROTOCOL = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
OTEL_EXPORTER_OTLP_HEADERS = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
OTEL_EXPORTER_OTLP_COMPRESSION = os.getenv("OTEL_EXPORTER_OTLP_COMPRESSION", "gzip")
OTEL_EXPORTER_OTLP_TIMEOUT = int(os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT", "10"))
OTEL_SAMPLER_TYPE = os.getenv("OTEL_SAMPLER_TYPE", "parentbased_traceidratio")
OTEL_SAMPLER_ARG = os.getenv("OTEL_SAMPLER_ARG", "0.1")
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "universal-dependency-resolver")
OTEL_SERVICE_VERSION = os.getenv("OTEL_SERVICE_VERSION", "1.0.0")
OTEL_RESOURCE_ATTRIBUTES = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")
ENV = os.getenv("ENV", "development")

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider, sampling
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter as OTLPHttpExporter,
    )
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    trace = None
    Resource = None
    TracerProvider = None
    sampling = None
    BatchSpanProcessor = None
    SimpleSpanProcessor = None
    OTLPHttpExporter = None
    FastAPIInstrumentor = None
    HTTPXClientInstrumentor = None

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as OTLPGrpcExporter,
    )
except ImportError:
    OTLPGrpcExporter = None


def _parse_resource_attributes(raw: str) -> dict:
    """Parse OTEL_RESOURCE_ATTRIBUTES (key1=val1,key2=val2) into a dict."""
    attrs = {}
    if not raw:
        return attrs
    for pair in raw.split(","):
        if "=" in pair:
            key, val = pair.split("=", 1)
            attrs[key.strip()] = val.strip()
    return attrs


def _create_sampler() -> Optional["sampling.Sampler"]:
    """Create a sampler based on OTEL_SAMPLER_TYPE and OTEL_SAMPLER_ARG."""
    if not _OTEL_AVAILABLE:
        return None
    sampler_type = OTEL_SAMPLER_TYPE
    sampler_arg = float(OTEL_SAMPLER_ARG)

    samplers = {
        "always_on": sampling.ALWAYS_ON,
        "always_off": sampling.ALWAYS_OFF,
        "traceidratio": sampling.TraceIdRatioBased(sampler_arg),
        "parentbased_traceidratio": sampling.ParentBased(
            sampling.TraceIdRatioBased(sampler_arg)
        ),
        "parentbased_always_on": sampling.ParentBased(sampling.ALWAYS_ON),
        "parentbased_always_off": sampling.ParentBased(sampling.ALWAYS_OFF),
    }

    return samplers.get(
        sampler_type, sampling.ParentBased(sampling.TraceIdRatioBased(0.1))
    )


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
        return OTLPHttpExporter(
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

    resource = Resource.create(resource_attrs)
    sampler = _create_sampler()
    provider = TracerProvider(resource=resource, sampler=sampler)

    exporter = _create_otlp_exporter()
    if exporter:
        if ENV == "development":
            provider.add_span_processor(SimpleSpanProcessor(exporter))
            logger.info("Using SimpleSpanProcessor (development mode)")
        else:
            provider.add_span_processor(
                BatchSpanProcessor(
                    exporter,
                    max_queue_size=2048,
                    max_export_batch_size=512,
                    schedule_delay_millis=5000,
                )
            )
            logger.info("Using BatchSpanProcessor (production mode)")

    trace.set_tracer_provider(provider)

    if app:
        try:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI instrumented for tracing")
        except Exception as e:
            logger.warning(f"Failed to instrument FastAPI: {e}")

    try:
        HTTPXClientInstrumentor().instrument()
        logger.info("HTTPX instrumented for tracing")
    except Exception as e:
        logger.warning(f"Failed to instrument HTTPX: {e}")

    logger.info(
        "OpenTelemetry tracing configured",
        endpoint=OTEL_EXPORTER_OTLP_ENDPOINT or "none (local only)",
        protocol=OTEL_EXPORTER_OTLP_PROTOCOL,
        sampler=f"{OTEL_SAMPLER_TYPE}({OTEL_SAMPLER_ARG})",
    )
