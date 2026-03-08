from http.server import HTTPServer

from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from prometheus_client import start_http_server

_api_httpd: HTTPServer | None = None
_worker_httpd: HTTPServer | None = None


def configure_api_metrics(port: int = 8001) -> MeterProvider:
    """Configure OTel metrics for the API process, exposing on given port."""
    global _api_httpd
    httpd, _ = start_http_server(port)
    _api_httpd = httpd
    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return provider


def configure_worker_metrics(port: int = 8002) -> MeterProvider:
    """Configure OTel metrics for the worker process, exposing on given port."""
    global _worker_httpd
    httpd, _ = start_http_server(port)
    _worker_httpd = httpd
    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return provider


def shutdown_api_metrics() -> None:
    """Shutdown the API metrics HTTP server."""
    if _api_httpd is not None:
        _api_httpd.shutdown()


def shutdown_worker_metrics() -> None:
    """Shutdown the worker metrics HTTP server."""
    if _worker_httpd is not None:
        _worker_httpd.shutdown()
