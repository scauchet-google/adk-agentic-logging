import importlib
import os
import sys
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

# Define mocks at module level
mock_otel_trace = MagicMock()


class MockTracerProvider:
    _instances: list["MockTracerProvider"] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.add_span_processor = MagicMock()
        MockTracerProvider._instances.append(self)


mock_otel_sdk_trace = MagicMock()
mock_otel_sdk_trace.trace.TracerProvider = MockTracerProvider

mock_gcp_exporter = MagicMock()
mock_genai_instrumentor = MagicMock()
# Mock the instrumentor class behavior
mock_instrumentor_instance = MagicMock()
mock_genai_instrumentor.GoogleGenAIInstrumentor.return_value = (
    mock_instrumentor_instance
)

mock_rich_exporter = MagicMock()

# Apply the patches to sys.modules BEFORE importing the code under test
sys.modules["opentelemetry"] = mock_otel_trace
sys.modules["opentelemetry.trace"] = mock_otel_trace.trace
sys.modules["opentelemetry.sdk"] = mock_otel_sdk_trace
sys.modules["opentelemetry.sdk.trace"] = mock_otel_sdk_trace.trace
sys.modules["opentelemetry.sdk.trace.export"] = mock_otel_sdk_trace.trace.export
sys.modules["opentelemetry.exporter.cloud_trace"] = mock_gcp_exporter
sys.modules["opentelemetry.instrumentation.google_genai"] = mock_genai_instrumentor
sys.modules["opentelemetry.exporter.richconsole"] = mock_rich_exporter

import adk_agentic_logging  # noqa: E402, I001
import adk_agentic_logging.otel_setup  # noqa: E402, I001

importlib.reload(adk_agentic_logging.otel_setup)


class TestLoggingConfig(unittest.TestCase):
    def setUp(self) -> None:
        # Reset mocks
        mock_otel_trace.trace.get_tracer_provider.return_value = MagicMock(spec=[])
        MockTracerProvider._instances = []
        mock_gcp_exporter.CloudTraceSpanExporter.reset_mock()
        instr = adk_agentic_logging.otel_setup.GoogleGenAIInstrumentor
        if instr:
            instr._is_instrumented_by_adk = False
        mock_instrumentor_instance.instrument.reset_mock()
        mock_rich_exporter.RichConsoleSpanExporter.reset_mock()

        # Reset instrumentation flag
        if hasattr(
            mock_genai_instrumentor.GoogleGenAIInstrumentor, "_is_instrumented_by_adk"
        ):
            delattr(
                mock_genai_instrumentor.GoogleGenAIInstrumentor,
                "_is_instrumented_by_adk",
            )

        # Clear env var
        if "OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED" in os.environ:
            del os.environ["OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED"]

    def test_configure_otel_default(self) -> None:
        # Default should enable console tracing
        adk_agentic_logging.configure_logging()

        self.assertEqual(len(MockTracerProvider._instances), 1)
        # Verify console exporter initialized
        mock_rich_exporter.RichConsoleSpanExporter.assert_called_once()
        # GCP should NOT be called
        mock_gcp_exporter.CloudTraceSpanExporter.assert_not_called()

    def test_configure_otel_google_enabled(self) -> None:
        with patch(
            "adk_agentic_logging.otel_setup.get_google_project_id"
        ) as mock_get_project:
            mock_get_project.return_value = "test-project"

            adk_agentic_logging.configure_logging(enable_google_tracing=True)

            # Verify provider registration
            self.assertEqual(len(MockTracerProvider._instances), 1)

            # Verify both exporters initialized
            mock_rich_exporter.RichConsoleSpanExporter.assert_called_once()
            mock_gcp_exporter.CloudTraceSpanExporter.assert_called_with(
                project_id="test-project"
            )

            # Verify instrumentation
            instrumentor = adk_agentic_logging.otel_setup.GoogleGenAIInstrumentor
            if instrumentor:
                instrumentor.assert_called()
                # Check that instrument() was called on the instance
                instrumentor.return_value.instrument.assert_called()

            # Verify env var
            self.assertEqual(
                os.environ.get("OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED"),
                "true",
            )

    def test_configure_otel_no_console(self) -> None:
        adk_agentic_logging.configure_logging(enable_console_tracing=False)
        self.assertEqual(len(MockTracerProvider._instances), 1)
        mock_rich_exporter.RichConsoleSpanExporter.assert_not_called()

    def test_external_provider_compatibility(self) -> None:
        # Simulate an existing SDK provider
        existing_provider = MockTracerProvider()
        # Mock get_tracer_provider to return this SDK provider
        mock_otel_trace.trace.get_tracer_provider.return_value = existing_provider

        adk_agentic_logging.configure_logging(enable_google_tracing=True)

        # Should NOT create a new provider (MockTracerProvider._instances already has 1)
        self.assertEqual(len(MockTracerProvider._instances), 1)

        # Verify GCP processor added to existing provider
        mock_gcp_exporter.CloudTraceSpanExporter.assert_called()
        self.assertTrue(existing_provider.add_span_processor.called)

    def test_double_initialization_guard(self) -> None:
        adk_agentic_logging.configure_logging(enable_google_tracing=True)

        # Reset specific mocks for second call
        mock_rich_exporter.RichConsoleSpanExporter.reset_mock()
        mock_gcp_exporter.CloudTraceSpanExporter.reset_mock()

        # Use the already created provider for the second call
        provider = MockTracerProvider._instances[0]
        mock_otel_trace.trace.get_tracer_provider.return_value = provider

        adk_agentic_logging.configure_logging(enable_google_tracing=True)

        # Should NOT call exporters again
        mock_rich_exporter.RichConsoleSpanExporter.assert_not_called()
        mock_gcp_exporter.CloudTraceSpanExporter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
