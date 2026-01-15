import json
from typing import Any, Dict, Generator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from adk_agentic_logging.adk.instrumentation import instrument_runner
from adk_agentic_logging.integrations.fastapi import AgenticLoggingMiddleware


# 1. Mock ADK Agent with different config formats
class MockAgent:
    def __init__(self, config_type: str = "direct") -> None:
        class MockModel:
            def __init__(self) -> None:
                self.model_name = "gemini-1.5-flash"
                if config_type == "direct":
                    self.temperature = 0.7
                elif config_type == "object":
                    class GenConfig:
                        def __init__(self) -> None:
                            self.temperature = 0.8
                    self.generation_config = GenConfig()
                elif config_type == "dict":
                    self.generation_config = {"temperature": 0.9}

        class MockInnerAgent:
            def __init__(self) -> None:
                self.name = "weather-agent"
                self.model = MockModel()

        self.agent = MockInnerAgent()

    @instrument_runner
    def run(
        self, runner_input: Dict[str, Any]
    ) -> Generator[Any, None, None]:
        yield {"text": "The temperature in Paris is 22°C."}


def run_test_with_agent(agent_instance: MockAgent, capsys: pytest.CaptureFixture[str], expected_temp: float) -> None:
    # Re-initialize app to use the new agent instance
    app = FastAPI()
    app.add_middleware(AgenticLoggingMiddleware)

    @app.post("/chat")
    async def chat(request: Request) -> Dict[str, Any]:
        body = await request.json()
        responses = list(agent_instance.run(body))
        return {"status": "ok", "responses_count": len(responses)}

    client = TestClient(app)
    payload = {"session_id": "session-123", "user_id": "user-456"}
    
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    
    captured = capsys.readouterr()
    log_lines = [line for line in captured.out.strip().split("\n") if line.strip()]
    
    found_agentic_log = False
    for line in log_lines:
        try:
            log_data = json.loads(line)
            if "http" in log_data and log_data["http"]["path"] == "/chat":
                found_agentic_log = True
                
                # Check gen_ai metadata
                assert log_data["gen_ai"]["temperature"] == expected_temp
                
                # Check adk metadata block
                assert "adk" in log_data
                assert log_data["adk"]["temperature"] == expected_temp
                
        except json.JSONDecodeError:
            continue
            
    assert found_agentic_log, "Could not find the agentic log line in output"


def test_temperature_direct(capsys: pytest.CaptureFixture[str]) -> None:
    run_test_with_agent(MockAgent("direct"), capsys, 0.7)


def test_temperature_object(capsys: pytest.CaptureFixture[str]) -> None:
    run_test_with_agent(MockAgent("object"), capsys, 0.8)


def test_temperature_dict(capsys: pytest.CaptureFixture[str]) -> None:
    run_test_with_agent(MockAgent("dict"), capsys, 0.9)
