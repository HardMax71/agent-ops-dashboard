from http.server import HTTPServer

from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from prometheus_client import start_http_server


def configure_metrics(port: int) -> tuple[HTTPServer, MeterProvider]:
    """Start Prometheus HTTP server and configure OTel MeterProvider.

    Returns the HTTPServer and MeterProvider — caller owns their lifecycle.
    """
    httpd, _ = start_http_server(port)
    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return httpd, provider


def shutdown_metrics(httpd: HTTPServer) -> None:
    """Shut down the metrics HTTP server and release the socket."""
    httpd.shutdown()
    httpd.server_close()
