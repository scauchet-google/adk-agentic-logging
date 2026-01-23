import logging
import os
from typing import Any, Optional, cast

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Import GCP Trace exporter safely
try:
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
except ImportError:
    CloudTraceSpanExporter = None  # type: ignore[assignment, misc]

# Import Google Cloud Logging safely
try:
    import google.cloud.logging
    from google.cloud.logging.handlers import CloudLoggingHandler
except ImportError:
    google = None  # type: ignore[assignment]
    CloudLoggingHandler = None

# Import Google GenAI instrumentation safely
try:
    import opentelemetry.instrumentation.google_genai as genai_instr

    GoogleGenAIInstrumentor = getattr(
        genai_instr,
        "GoogleGenAIInstrumentor",
        getattr(genai_instr, "GoogleGenAiSdkInstrumentor", None),
    )
except ImportError:
    GoogleGenAIInstrumentor = None

from opentelemetry.exporter.richconsole import RichConsoleSpanExporter

from adk_agentic_logging.core.metadata import get_google_project_id

logger = logging.getLogger(__name__)


def configure_otel(
    enable_google_tracing: bool = False,
    enable_console_tracing: bool = True,
    enable_cloud_logging: bool = False,
    project_id: Optional[str] = None,
) -> None:
    """
    Configures OpenTelemetry with a 'Multi-Processor' strategy.
    Safe to call even if a TracerProvider is already set.
    """
    # 1. Acquire or Initialize the TracerProvider
    provider = trace.get_tracer_provider()

    if not hasattr(provider, "add_span_processor"):
        # Case A: No real SDK provider exists (it's likely NoOp or Proxy).
        # We must create one and set it as global.
        provider = TracerProvider()
        trace.set_tracer_provider(provider)

    # Track which processors we've added to this provider instance to avoid duplicates
    if not hasattr(provider, "_adk_processors"):
        setattr(provider, "_adk_processors", set())  # noqa: B010

    adk_processors: set[str] = provider._adk_processors  # type: ignore[attr-defined]

    # 2. Configure Console Tracing (Local Debugging)
    if enable_console_tracing and "console" not in adk_processors:
        console_exporter = RichConsoleSpanExporter()
        cast(Any, provider).add_span_processor(
            BatchSpanProcessor(
                console_exporter,
                schedule_delay_millis=500,
                max_export_batch_size=10,
            )
        )
        adk_processors.add("console")
        logger.debug("Console tracing (Rich) activated.")

    # 3. Configure Google Cloud Tracing (Production)
    if enable_google_tracing and "google" not in adk_processors:
        if CloudTraceSpanExporter is None:
            logger.warning(
                "enable_google_tracing=True but "
                "opentelemetry-exporter-gcp-trace is not installed. "
                "Please install it via "
                "`pip install adk-agentic-logging[google-adk]`."
            )
        else:
            # Resolve Project ID
            final_project_id = project_id or get_google_project_id()

            if final_project_id:
                exporter = cast(Any, CloudTraceSpanExporter)(
                    project_id=final_project_id
                )
            else:
                exporter = cast(Any, CloudTraceSpanExporter)()

            cast(Any, provider).add_span_processor(BatchSpanProcessor(exporter))
            adk_processors.add("google")
            logger.info(
                "Google Cloud Trace configured "
                f"(Project: {final_project_id or 'auto-detected'})."
            )

    # 4. Auto-instrument Google GenAI if available
    if GoogleGenAIInstrumentor is not None:
        if not getattr(GoogleGenAIInstrumentor, "_is_instrumented_by_adk", False):
            GoogleGenAIInstrumentor().instrument()
            GoogleGenAIInstrumentor._is_instrumented_by_adk = True
            logger.info("Google GenAI instrumentation activated.")
    else:
        logger.debug(
            "opentelemetry-instrumentation-google-genai not installed. "
            "Skipping auto-instrumentation."
        )

    # 5. Configure Google Cloud Logging if requested
    if enable_cloud_logging:
        final_project_id = project_id or get_google_project_id()
        configure_cloud_logging(project_id=final_project_id)

    # 6. Inject environment variables for correlation
    os.environ.setdefault("OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED", "true")


class GCPTraceFilter(logging.Filter):
    """
    Injects GCP-specific trace and span IDs into the log record for correlation.
    GCP requires the trace field to be in the format:
    projects/[PROJECT_ID]/traces/[TRACE_ID]
    """

    def __init__(self, project_id: Optional[str] = None):
        super().__init__()
        self.project_id = project_id or get_google_project_id()

    def filter(self, record: logging.LogRecord) -> bool:
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            trace_id = trace.format_trace_id(span_context.trace_id)
            span_id = trace.format_span_id(span_context.span_id)

            # GCP Trace Correlation format
            if self.project_id:
                record.trace = f"projects/{self.project_id}/traces/{trace_id}"
            else:
                record.trace = trace_id

            record.span_id = span_id
            record.trace_sampled = span_context.trace_flags.sampled

        # Prevent logging loops by excluding logs from the logging/trace clients themselves
        if record.name.startswith(("google", "opentelemetry", "urllib3")):
            return False

        return True


def configure_cloud_logging(project_id: Optional[str] = None) -> None:
    """
    Configures the native Google Cloud Logging handler.
    Correlates logs with traces if running in GCP or if trace context is available.
    """
    if CloudLoggingHandler is None:
        logger.warning(
            "enable_cloud_logging=True but `google-cloud-logging` is not installed. "
            "Please install it via `pip install adk-agentic-logging[google-adk]`."
        )
        return

    try:
        client = google.cloud.logging.Client(project=project_id)
        # We use the default handler which is designed for GCP environments.
        # It automatically attaches trace/span IDs if the OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED
        # or similar correlation mechanisms are active.
        handler = CloudLoggingHandler(client)

        # Attach the GCPTraceFilter for explicit correlation
        handler.addFilter(GCPTraceFilter(project_id=project_id))

        # Add to the root logger to catch all application logs,
        # or we could be more surgical.
        logging.getLogger().addHandler(handler)

        logger.info(
            "Google Cloud Logging handler attached "
            f"(Project: {project_id or 'auto-detected'})."
        )
    except Exception as e:
        logger.error(f"Failed to configure Google Cloud Logging: {e}")


def configure_google_tracing(enable_google_tracing: bool = False) -> None:
    """Legacy wrapper for backward compatibility."""
    configure_otel(enable_google_tracing=enable_google_tracing)
