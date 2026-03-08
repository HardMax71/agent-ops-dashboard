from http.server import HTTPServer

from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from prometheus_client import start_http_server

_api_httpd: HTTPServer | None = None
_api_provider: MeterProvider | None = None
_worker_httpd: HTTPServer | None = None
_worker_provider: MeterProvider | None = None


def configure_api_metrics(port: int = 8001) -> MeterProvider:
    """Configure OTel metrics for the API process, exposing on given port."""
    global _api_httpd, _api_provider  # noqa: PLW0603
    if _api_httpd is not None and _api_provider is not None:
        return _api_provider
    httpd, _ = start_http_server(port)
    _api_httpd = httpd
    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    _api_provider = provider
    return provider


def configure_worker_metrics(port: int = 8002) -> MeterProvider:
    """Configure OTel metrics for the worker process, exposing on given port."""
    global _worker_httpd, _worker_provider  # noqa: PLW0603
    if _worker_httpd is not None and _worker_provider is not None:
        return _worker_provider
    httpd, _ = start_http_server(port)
    _worker_httpd = httpd
    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    _worker_provider = provider
    return provider


def shutdown_api_metrics() -> None:
    """Shut down the API metrics HTTP server."""
    global _api_httpd, _api_provider  # noqa: PLW0603
    if _api_httpd is not None:
        _api_httpd.shutdown()
        _api_httpd.server_close()
        _api_httpd = None
        _api_provider = None


def shutdown_worker_metrics() -> None:
    """Shut down the worker metrics HTTP server."""
    global _worker_httpd, _worker_provider  # noqa: PLW0603
    if _worker_httpd is not None:
        _worker_httpd.shutdown()
        _worker_httpd.server_close()
        _worker_httpd = None
        _worker_provider = None
