from typing import Any, Dict, Generator

from adk_agentic_logging.adk.instrumentation import instrument_runner
from adk_agentic_logging.core.context import log_ctx


class MockUsage:
    def __init__(self, tokens: int) -> None:
        self.total_tokens = tokens

class MockChunk:
    usage: Any
    usage_metadata: Any
    def __init__(self, usage: Any = None, usage_metadata: Any = None) -> None:
        if usage:
            self.usage = usage
        if usage_metadata:
            self.usage_metadata = usage_metadata

def test_usage_metadata_extraction() -> None:
    """Verify that usage_metadata is also checked for tokens."""
    log_ctx.clear()
    
    class Agent:
        @instrument_runner
        def run(self, input_obj: Dict[str, Any]) -> Generator[Any, None, None]:
            yield MockChunk(usage_metadata=MockUsage(150))
    
    agent = Agent()
    list(agent.run({"session_id": "test"}))
    
    ctx = log_ctx.get_all()
    assert ctx["adk"]["total_tokens"] == 150

def test_dict_usage_extraction() -> None:
    """Verify that dictionary-like access works for usage."""
    log_ctx.clear()
    
    class Agent:
        @instrument_runner
        def run(self, input_obj: Dict[str, Any]) -> Generator[Any, None, None]:
            yield {"usage": {"total_tokens": 200}}
    
    agent = Agent()
    list(agent.run({"session_id": "test"}))
    
    ctx = log_ctx.get_all()
    # Current implementation will fail this (total_tokens will be 0)
    assert ctx["adk"]["total_tokens"] == 200

def test_dict_usage_metadata_extraction() -> None:
    """Verify that dictionary-like access works for usage_metadata."""
    log_ctx.clear()
    
    class Agent:
        @instrument_runner
        def run(self, input_obj: Dict[str, Any]) -> Generator[Any, None, None]:
            yield {"usage_metadata": {"total_tokens": 250}}
    
    agent = Agent()
    list(agent.run({"session_id": "test"}))
    
    ctx = log_ctx.get_all()
    # Current implementation will fail this (total_tokens will be 0)
    assert ctx["adk"]["total_tokens"] == 250
