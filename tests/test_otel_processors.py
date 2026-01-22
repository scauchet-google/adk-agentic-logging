from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from adk_agentic_logging.otel.processors import VertexAISanitizer


def test_vertex_ai_sanitizer_removes_noisy_keys() -> None:
    # Setup
    provider = TracerProvider()
    memory_exporter = InMemorySpanExporter()

    # Add our sanitizer
    provider.add_span_processor(VertexAISanitizer())
    # Add a processor to capture spans
    provider.add_span_processor(SimpleSpanProcessor(memory_exporter))

    tracer = provider.get_tracer(__name__)

    # Start a span with noisy attributes
    with tracer.start_as_current_span("test-span") as span:
        span.set_attribute("gcp.vertex.agent.llm_request", '{"prompt": "lots of text"}')
        span.set_attribute(
            "gcp.vertex.agent.llm_response", '{"response": "even more text"}'
        )
        span.set_attribute("other.attribute", "keep me")

    # Check exported spans
    exported_spans = memory_exporter.get_finished_spans()
    assert len(exported_spans) == 1
    exported_span = exported_spans[0]

    # Verify noisy keys are removed
    assert exported_span.attributes is not None
    assert "gcp.vertex.agent.llm_request" not in exported_span.attributes
    assert "gcp.vertex.agent.llm_response" not in exported_span.attributes

    # Verify other keys are preserved
    from typing import Any, cast

    assert cast(Any, exported_span.attributes)["other.attribute"] == "keep me"


def test_vertex_ai_sanitizer_handles_no_attributes() -> None:
    provider = TracerProvider()
    memory_exporter = InMemorySpanExporter()
    provider.add_span_processor(VertexAISanitizer())
    provider.add_span_processor(SimpleSpanProcessor(memory_exporter))

    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("empty-span"):
        pass

    exported_spans = memory_exporter.get_finished_spans()
    assert len(exported_spans) == 1
    assert not exported_spans[0].attributes
