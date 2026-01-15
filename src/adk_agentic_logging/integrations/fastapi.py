import json
import time
from typing import Any
import opentelemetry.trace as trace

from fastapi import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from adk_agentic_logging.core.context import log_ctx
from adk_agentic_logging.core.metadata import get_google_project_id


class AgenticLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.project_id = get_google_project_id()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        log_ctx.clear()
        start_time = time.time()

        tracer = trace.get_tracer(__name__)
        span_name = f"{request.method} {request.url.path}"

        with tracer.start_as_current_span(span_name) as span:
            # Initialize context with OTel tracing
            log_ctx.initialize_with_otel(self.project_id)

            # Capture initial HTTP metadata
            http_meta = {
                "method": request.method,
                "path": request.url.path,
            }
            log_ctx.add("http", http_meta)
            for k, v in http_meta.items():
                span.set_attribute(f"http.{k}", v)

            async def send_wrapper(message: Any) -> None:
                if message["type"] == "http.response.start":
                    status = message["status"]
                    duration = round((time.time() - start_time) * 1000, 2)
                    log_ctx.add(
                        "http",
                        {
                            **log_ctx.get_all().get("http", {}),
                            "status": status,
                            "duration_ms": duration,
                        },
                    )
                    span.set_attribute("http.status_code", status)
                    span.set_attribute("http.duration_ms", duration)
                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as e:
                log_ctx.record_exception(e)
                duration = round((time.time() - start_time) * 1000, 2)
                log_ctx.add(
                    "http",
                    {
                        **log_ctx.get_all().get("http", {}),
                        "status": 500,
                        "duration_ms": duration,
                    },
                )
                span.set_attribute("http.status_code", 500)
                span.set_attribute("http.duration_ms", duration)
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                raise e
            finally:
                # Add all remaining context as span attributes
                for key, val in log_ctx.get_all().items():
                    if isinstance(val, dict):
                        for k, v in val.items():
                            attr_val = str(v)
                            if len(attr_val) > 1024:
                                attr_val = attr_val[:1024] + "... [truncated]"
                            span.set_attribute(f"{key}.{k}", attr_val)
                    else:
                        attr_val = str(val)
                        if len(attr_val) > 1024:
                            attr_val = attr_val[:1024] + "... [truncated]"
                        span.set_attribute(key, attr_val)
                self._emit_log()

    def _emit_log(self) -> None:
        ctx = log_ctx.get_all()
        if not ctx:
            return

        final_log = {
            "severity": ctx.get("severity", "INFO"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": "Request processed",
            **ctx,
        }
        print(json.dumps(final_log))
