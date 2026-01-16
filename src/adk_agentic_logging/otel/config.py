from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from adk_agentic_logging.otel.processors import VertexAISanitizer


def configure_adk_telemetry(project_id: str) -> None:
    """
    Sets up OTel with Cloud Trace export and Vertex AI sanitization.
    
    Args:
        project_id: The GCP project ID to export traces to.
    """
    provider = TracerProvider()
    
    # 1. Sanitize FIRST (remove bloat)
    provider.add_span_processor(VertexAISanitizer())
    
    # 2. Export SECOND (send lightweight traces)
    # CloudTraceSpanExporter sends spans to Google Cloud Trace.
    exporter = CloudTraceSpanExporter(project_id=project_id)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    
    trace.set_tracer_provider(provider)
