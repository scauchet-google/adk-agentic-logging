import json
from typing import Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adk_agentic_logging.integrations.fastapi import AgenticLoggingMiddleware

app = FastAPI()
app.add_middleware(AgenticLoggingMiddleware)


@app.get("/test")
async def read_test() -> Dict[str, str]:
    return {"message": "ok"}


@app.get("/error")
async def read_error() -> None:
    raise ValueError("oops")


def test_fastapi_middleware_success(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="adk.agentic")
    client = TestClient(app)
    response = client.get("/test")
    assert response.status_code == 200

    # Ensure we got exactly one log record from our middleware
    log_records = [rec for rec in caplog.records if rec.name == "adk.agentic"]
    assert len(log_records) > 0
    log_line = json.loads(log_records[-1].message)

    assert log_line["severity"] == "INFO"
    assert log_line["http"]["method"] == "GET"
    assert log_line["http"]["path"] == "/test"
    assert log_line["http"]["status"] == 200
    assert "duration_ms" in log_line["http"]


def test_fastapi_middleware_error(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="adk.agentic")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/error")
    assert response.status_code == 500

    log_records = [rec for rec in caplog.records if rec.name == "adk.agentic"]
    assert len(log_records) > 0
    log_line = json.loads(log_records[-1].message)

    assert log_line["severity"] == "ERROR"
    assert log_line["error"]["type"] == "ValueError"
    assert log_line["error"]["message"] == "oops"
