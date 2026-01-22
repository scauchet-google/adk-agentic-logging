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

    # 5. Inject environment variables for correlation
    os.environ.setdefault("OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED", "true")


def configure_google_tracing(enable_google_tracing: bool = False) -> None:
    """Legacy wrapper for backward compatibility."""
    configure_otel(enable_google_tracing=enable_google_tracing)
