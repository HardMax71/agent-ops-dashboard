from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from prometheus_client import start_http_server


def configure_api_metrics(port: int = 8001) -> MeterProvider:
    """Configure OTel metrics for the API process, exposing on given port."""
    start_http_server(port)
    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return provider


def configure_worker_metrics(port: int = 8002) -> MeterProvider:
    """Configure OTel metrics for the worker process, exposing on given port."""
    start_http_server(port)
    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return provider
