from typing import Optional

from adk_agentic_logging.core.context import log_ctx
from adk_agentic_logging.otel_setup import configure_otel


def configure_logging(
    enable_google_tracing: bool = False,
    enable_console_tracing: bool = True,
    enable_cloud_logging: bool = False,
    project_id: Optional[str] = None,
) -> None:
    """
    Unified entry point for configuring adk-agentic-logging.

    Args:
        enable_google_tracing: If True, enables Google Cloud Tracing
            (requires [google-adk] extra).
        enable_console_tracing: If True, enables Console Tracing
            (RichConsoleExporter).
        enable_cloud_logging: If True, enables native Google Cloud Logging
            (requires [google-adk] extra).
        project_id: Optional Google Cloud Project ID.
    """
    configure_otel(
        enable_google_tracing=enable_google_tracing,
        enable_console_tracing=enable_console_tracing,
        enable_cloud_logging=enable_cloud_logging,
        project_id=project_id,
    )


__all__ = ["log_ctx", "configure_logging"]
