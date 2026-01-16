import asyncio
import json
import time
from typing import Any, Callable, Coroutine, cast

from django.http import HttpRequest, HttpResponse

from adk_agentic_logging.core.context import log_ctx
from adk_agentic_logging.core.logger import logger
from adk_agentic_logging.core.metadata import get_google_project_id
from adk_agentic_logging.core.serialization import default_serializer


class AgenticLoggingMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response
        self.project_id = get_google_project_id()
        self._is_coroutine = asyncio.iscoroutinefunction(get_response)

    def __call__(self, request: HttpRequest) -> Any:
        if self._is_coroutine:
            return self._acall(request)

        log_ctx.clear()
        start_time = time.time()
        log_ctx.initialize_with_otel(self.project_id)
        log_ctx.add(
            "http",
            {
                "method": request.method,
                "path": request.path,
            },
        )

        try:
            response = self.get_response(request)
            self._finalize_http(response, start_time)
            return response
        except Exception as e:
            self._handle_exception(e, start_time)
            raise e
        finally:
            self._emit_log()

    async def _acall(self, request: HttpRequest) -> HttpResponse:
        log_ctx.clear()
        start_time = time.time()
        log_ctx.initialize_with_otel(self.project_id)
        log_ctx.add(
            "http",
            {
                "method": request.method,
                "path": request.path,
            },
        )

        try:
            response = await cast(
                Coroutine[Any, Any, HttpResponse], self.get_response(request)
            )
            self._finalize_http(response, start_time)
            return response
        except Exception as e:
            self._handle_exception(e, start_time)
            raise e
        finally:
            self._emit_log()

    def _finalize_http(self, response: HttpResponse, start_time: float) -> None:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        http_ctx = log_ctx.get_all().get("http", {})
        http_ctx.update({
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        })
        log_ctx.add("http", http_ctx)

    def _handle_exception(self, e: Exception, start_time: float) -> None:
        log_ctx.record_exception(e)
        duration_ms = round((time.time() - start_time) * 1000, 2)
        http_ctx = log_ctx.get_all().get("http", {})
        http_ctx.update({
            "status_code": 500,
            "duration_ms": duration_ms,
        })
        log_ctx.add("http", http_ctx)

    def _emit_log(self) -> None:
        ctx = log_ctx.get_all()
        if not ctx:
            return

        final_log = {
            "severity": ctx.pop("severity", "INFO"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **ctx,
        }
        logger.info(json.dumps(final_log, default=default_serializer))
