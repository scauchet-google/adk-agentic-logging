import contextvars
from typing import Any, Dict, Optional

import opentelemetry.trace as trace

# The context bucket for the request
_log_context: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "adk_log_context", default=None
)


class LogContext:
    def _get_ctx(self) -> Dict[str, Any]:
        ctx = _log_context.get()
        if ctx is None:
            ctx = {}
            _log_context.set(ctx)
        return ctx

    def add(self, key: str, value: Any) -> None:
        """
        Adds a key-value pair to the current request context.
        Supports dot notation for nesting (e.g., 'gen_ai.usage.total_tokens').
        Keys starting with 'logging.googleapis.com' are kept flat.
        """
        ctx = self._get_ctx().copy()

        if "." in key and not key.startswith("logging.googleapis.com"):
            parts = key.split(".")
            d = ctx
            for part in parts[:-1]:
                if part not in d or not isinstance(d[part], dict):
                    d[part] = {}
                d = d[part]
            d[parts[-1]] = value
        else:
            ctx[key] = value

        _log_context.set(ctx)

        # Also set as span attribute if a span is active
        span = trace.get_current_span()
        if span and span.is_recording():
            # For spans, we always use dot notation as attributes are flat
            if isinstance(value, dict):
                # If we passed a dict, we need to flatten it for the span
                def _flatten_set(prefix: str, v: Any) -> None:
                    if isinstance(v, dict):
                        for k2, v2 in v.items():
                            _flatten_set(f"{prefix}.{k2}", v2)
                    else:
                        span.set_attribute(prefix, str(v))

                _flatten_set(key, value)
            else:
                span.set_attribute(key, str(value))

    def add_content(self, key: str, value: Any, snippet_length: int = 50) -> None:
        """
        Implementation of the 'Snippet' strategy.
        Stores full value in Logs, but truncated version in Trace Span.
        """
        # Store full value in context
        self.add(key, value)

        # Truncate for span if it's a string
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid and isinstance(value, str):
            snippet = value
            if len(value) > snippet_length:
                snippet = value[:snippet_length] + "..."
            span.set_attribute(key, snippet)

    def enrich(self, **kwargs: Any) -> None:
        """Convenience method to add multiple attributes to the context."""
        for key, value in kwargs.items():
            self.add(key, value)

    def get_all(self) -> Dict[str, Any]:
        """Returns all data in the current context."""
        return self._get_ctx()

    def clear(self) -> None:
        """Clears the context."""
        _log_context.set(None)

    def record_exception(self, exc: BaseException) -> None:
        """Standardized exception recording."""
        error_info = {
            "type": exc.__class__.__name__,
            "message": str(exc),
            "module": exc.__class__.__module__,
        }
        self.add("error", error_info)
        self.add("severity", "ERROR")

    def initialize_with_otel(self, project_id: Optional[str] = None) -> None:
        """Injects OTel trace and span IDs if available."""
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            span_context = span.get_span_context()
            trace_id = format(span_context.trace_id, "032x")
            span_id = format(span_context.span_id, "016x")

            if project_id:
                # GCP standard trace format
                trace_url = f"projects/{project_id}/traces/{trace_id}"
                self.add("logging.googleapis.com/trace", trace_url)
            else:
                self.add("logging.googleapis.com/trace", trace_id)

            self.add("logging.googleapis.com/spanId", span_id)


log_ctx = LogContext()
