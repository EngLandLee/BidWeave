# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed observability configuration; no warranty.
"""Opt-in OpenTelemetry providers for the API process."""

from __future__ import annotations

import os

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def _enabled() -> bool:
    return os.getenv("OTEL_ENABLED", "false").strip().lower() == "true"


def _signal_endpoint(endpoint: str, signal: str) -> str:
    endpoint = endpoint.rstrip("/")
    suffix = f"/v1/{signal}"
    return endpoint if endpoint.endswith(suffix) else endpoint + suffix


def configure_observability(
    app: FastAPI,
) -> tuple[TracerProvider, MeterProvider] | None:
    """Instrument FastAPI/HTTPX and export traces/metrics when explicitly enabled.

    Exporters use OTLP over HTTP and do not configure request/response body or
    credential capture.  Provider shutdown remains the caller's responsibility.
    """
    if not _enabled():
        return None

    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"
    ).strip()
    resource = Resource.create({"service.name": "bidweave-api"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=_signal_endpoint(endpoint, "traces"))
        )
    )

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=_signal_endpoint(endpoint, "metrics"))
            )
        ],
    )

    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=tracer_provider, meter_provider=meter_provider
    )
    HTTPXClientInstrumentor().instrument(
        tracer_provider=tracer_provider, meter_provider=meter_provider
    )
    return tracer_provider, meter_provider
