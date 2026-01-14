import json
import time
from typing import Any, Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from adk_agentic_logging.core.context import log_ctx
from adk_agentic_logging.core.metadata import get_google_project_id


class AgenticLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any):
        super().__init__(app)
        self.project_id = get_google_project_id()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
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

        try:
            response = await call_next(request)
            log_ctx.add(
                "http",
                {
                    **log_ctx.get_all().get("http", {}),
                    "status": response.status_code,
                    "duration_ms": round((time.time() - start_time) * 1000, 2),
                },
            )
            return response
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
