import json
from typing import Any, Dict, Generator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from adk_agentic_logging.adk.instrumentation import instrument_runner
from adk_agentic_logging.integrations.fastapi import AgenticLoggingMiddleware


# 1. Mock ADK Agent
class MockAgent:
    @instrument_runner
    def run(self, runner_input: Dict[str, Any]) -> Generator[Any, None, None]:
        # Simulate some usage metrics retrieval
        class MockUsage:
            def __init__(self) -> None:
                self.total_tokens = 100

        class MockChunk:
            def __init__(self, text: str) -> None:
                self.text = text
                self.usage = MockUsage()
                self.tool_calls: list[Any] = []

        yield {"text": "Hello"}
        yield {"text": " world"}
        # Final chunk with metrics
        yield MockChunk("!")


# 2. FastAPI App
app = FastAPI()
app.add_middleware(AgenticLoggingMiddleware)

agent = MockAgent()


@app.post("/chat")
async def chat(request: Request) -> Dict[str, Any]:
    body = await request.json()
    # Simulate ADK runner execution
    responses = list(agent.run(body))
    return {"status": "ok", "responses_count": len(responses)}


def test_fastapi_adk_integration(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="adk.agentic")
    client = TestClient(app)

    # ADK-like payload
    payload = {"session_id": "session-123", "user_id": "user-456", "message": "hello"}

    response = client.post("/chat", json=payload)
    assert response.status_code == 200

    # Ensure we got exactly one log record from our middleware
    log_records = [rec for rec in caplog.records if rec.name == "adk.agentic"]
    assert len(log_records) > 0

    found_agentic_log = False
    for rec in log_records:
        try:
            log_data = json.loads(rec.message)
            if "http" in log_data and log_data["http"]["path"] == "/chat":
                found_agentic_log = True
                # Check FastAPI metadata
                assert log_data["http"]["method"] == "POST"
                assert log_data["http"]["status"] == 200

                # Check ADK metadata (captured via instrument_runner)
                assert "adk" in log_data
                assert log_data["adk"]["session_id"] == "session-123"
                assert log_data["adk"]["user_id"] == "user-456"

                # Check ADK metrics (captured via _wrap_generator in instrument_runner)
                # total_tokens should be 100 as per MockUsage
                assert log_data["adk"]["total_tokens"] == 100
        except json.JSONDecodeError:
            continue

    assert found_agentic_log, "Could not find the agentic log line in output"
