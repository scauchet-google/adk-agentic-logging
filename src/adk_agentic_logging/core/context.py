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
        """Adds a key-value pair to the current request context."""
        ctx = self._get_ctx().copy()
        ctx[key] = value
        _log_context.set(ctx)

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
                trace_url = f"projects/{project_id}/traces/{trace_id}"
                self.add("logging.googleapis.com/trace", trace_url)
            else:
                self.add("logging.googleapis.com/trace", trace_id)

            self.add("logging.googleapis.com/spanId", span_id)


log_ctx = LogContext()
