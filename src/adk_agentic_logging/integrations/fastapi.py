import json
import time
from typing import Any, Awaitable, Callable

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

        # Initialize context with OTel tracing
        log_ctx.initialize_with_otel(self.project_id)

        # Capture initial HTTP metadata
        log_ctx.add(
            "http",
            {
                "method": request.method,
                "path": request.url.path,
            },
        )

        async def send_wrapper(message: Any) -> None:
            if message["type"] == "http.response.start":
                status = message["status"]
                log_ctx.add(
                    "http",
                    {
                        **log_ctx.get_all().get("http", {}),
                        "status": status,
                        "duration_ms": round((time.time() - start_time) * 1000, 2),
                    },
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            log_ctx.record_exception(e)
            log_ctx.add(
                "http",
                {
                    **log_ctx.get_all().get("http", {}),
                    "status": 500,
                    "duration_ms": round((time.time() - start_time) * 1000, 2),
                },
            )
            raise e
        finally:
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
