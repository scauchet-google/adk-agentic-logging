import json
import time
from typing import Optional

from flask import Flask, Response, g, request

from adk_agentic_logging.core.context import log_ctx
from adk_agentic_logging.core.metadata import get_google_project_id


class AgenticLogging:
    def __init__(self, app: Optional[Flask] = None):
        self.project_id = get_google_project_id()
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        app.teardown_request(self._teardown_request)

    def _before_request(self) -> None:
        log_ctx.clear()
        g._start_time = time.time()
        log_ctx.initialize_with_otel(self.project_id)
        log_ctx.add(
            "http",
            {
                "method": request.method,
                "path": request.path,
            },
        )

    def _after_request(self, response: Response) -> Response:
        curr_time = time.time()
        start_time = getattr(g, "_start_time", curr_time)
        duration_ms = round((curr_time - start_time) * 1000, 2)
        log_ctx.add(
            "http",
            {
                **log_ctx.get_all().get("http", {}),
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    def _teardown_request(self, exception: Optional[BaseException] = None) -> None:
        if exception:
            log_ctx.record_exception(exception)

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
