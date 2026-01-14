import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from adk_agentic_logging.integrations.fastapi import AgenticLoggingMiddleware

app = FastAPI()
app.add_middleware(AgenticLoggingMiddleware)


@app.get("/test")
async def read_test():
    return {"message": "ok"}


@app.get("/error")
async def read_error():
    raise ValueError("oops")


def test_fastapi_middleware_success(capsys):
    client = TestClient(app)
    response = client.get("/test")
    assert response.status_code == 200

    captured = capsys.readouterr()
    log_line = json.loads(captured.out.strip())

    assert log_line["severity"] == "INFO"
    assert log_line["http"]["method"] == "GET"
    assert log_line["http"]["path"] == "/test"
    assert log_line["http"]["status"] == 200
    assert "duration_ms" in log_line["http"]


def test_fastapi_middleware_error(capsys):
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/error")
    assert response.status_code == 500

    captured = capsys.readouterr()
    log_line = json.loads(captured.out.strip())

    assert log_line["severity"] == "ERROR"
    assert log_line["error"]["type"] == "ValueError"
    assert log_line["error"]["message"] == "oops"
