from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor


class VertexAISanitizer(SpanProcessor):
    """
    SpanProcessor that removes noisy Vertex AI attributes from traces.
    Specifically targets gcp.vertex.agent.llm_request and gcp.vertex.agent.llm_response
    which can contain massive JSON payloads already captured in logs.
    """

    def on_end(self, span: ReadableSpan) -> None:
        """
        Interception point after span finishes but before export.
        Surgically removes blocked keys from span attributes.
        """
        if not span.attributes:
            return

        # Blocklist of keys to remove
        blocklist = [
            "gcp.vertex.agent.llm_request",
            "gcp.vertex.agent.llm_response",
        ]

        for key in blocklist:
            if key in span.attributes:
                # In OTel SDK, ReadableSpan is often the Span object itself.
                # Span.attributes is a mappingproxy, but Span._attributes is the actual 
                # storage (BoundedAttributes).
                if hasattr(span, "_attributes"):
                    try:
                        del span._attributes[key]
                    except (KeyError, TypeError):
                        pass
