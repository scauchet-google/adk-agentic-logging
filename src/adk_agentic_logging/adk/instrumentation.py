import functools
import inspect
from typing import Any, AsyncGenerator, Callable, Generator, Iterable, TypeVar, cast, AsyncIterable, List, Dict

from adk_agentic_logging.adk.extractors import (
    extract_adk_metadata,
    extract_agent_config,
    extract_tool_calls_info
)
from adk_agentic_logging.core.context import log_ctx

F = TypeVar("F", bound=Callable[..., Any])


def instrument_runner(func: F) -> F:
    """
    Decorator for ADK Runner.run method.
    Captures session/user IDs, Agent Configuration, and wraps generators for 
    metric accumulation (tokens, tool calls).
    Supports both synchronous and asynchronous methods/generators.
    """

    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        _prepare_log_ctx(*args, **kwargs)
        try:
            result = await func(*args, **kwargs)

            # Handle streaming response
            if inspect.isasyncgen(result) or isinstance(result, AsyncIterable):
                return _wrap_async_generator(result)

            # Handle direct response
            _capture_metrics(result)
            return result
        except Exception as e:
            log_ctx.record_exception(e)
            raise e

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        _prepare_log_ctx(*args, **kwargs)
        try:
            result = func(*args, **kwargs)

            # Handle streaming response
            if inspect.isgenerator(result) or isinstance(result, Iterable):
                return _wrap_generator(result)

            # Handle direct response
            _capture_metrics(result)
            return result
        except Exception as e:
            log_ctx.record_exception(e)
            raise e

    if inspect.iscoroutinefunction(func):
        return cast(F, async_wrapper)
    return cast(F, sync_wrapper)


def _prepare_log_ctx(*args: Any, **kwargs: Any) -> None:
    """Extracts metadata from input and adds it to the log context."""
    # 1. Extract Agent Configuration from the runner instance (self)
    if args:
        runner_instance = args[0]
        agent_config = extract_agent_config(runner_instance)
        if agent_config:
            log_ctx.add("gen_ai", agent_config)

    # 2. Extract Input Metadata (session_id, user_id, etc.)
    # Usually first arg after self or named kwargs
    input_obj = args[1] if len(args) > 1 else kwargs.get("runner_input")
    if not input_obj and kwargs:
        input_obj = kwargs

    adk_meta = extract_adk_metadata(input_obj)
    
    # Enrich with temperature if found in agent_config
    if "temperature" in agent_config:
        adk_meta["temperature"] = agent_config["temperature"]
        
    log_ctx.add("adk", adk_meta)


def _wrap_generator(gen: Iterable[Any]) -> Generator[Any, None, None]:
    """Wraps an ADK response generator to accumulate metrics."""
    total_tokens = 0
    tool_calls: List[Dict[str, Any]] = []

    try:
        for chunk in gen:
            total_tokens, tool_calls = _process_chunk(chunk, total_tokens, tool_calls)
            yield chunk
    finally:
        _finalize_metrics(total_tokens, tool_calls)


async def _wrap_async_generator(gen: AsyncIterable[Any]) -> AsyncGenerator[Any, None]:
    """Wraps an ADK response async generator to accumulate metrics."""
    total_tokens = 0
    tool_calls: List[Dict[str, Any]] = []

    try:
        async for chunk in gen:
            total_tokens, tool_calls = _process_chunk(chunk, total_tokens, tool_calls)
            yield chunk
    finally:
        _finalize_metrics(total_tokens, tool_calls)


def _process_chunk(chunk: Any, total_tokens: int, tool_calls: List[Dict[str, Any]]) -> tuple[int, List[Dict[str, Any]]]:
    """Extracts metrics from a single chunk."""
    # 1. Extract Token Usage
    # Support both 'usage' and 'usage_metadata'
    # Support both attribute and dictionary access
    usage = None
    for attr in ["usage", "usage_metadata"]:
        usage = getattr(chunk, attr, None)
        if usage is None and isinstance(chunk, dict):
            usage = chunk.get(attr)
        if usage:
            break

    if usage:
        # Support both attribute and dictionary access for total_tokens
        new_tokens = getattr(usage, "total_tokens", None)
        if new_tokens is None and isinstance(usage, dict):
            new_tokens = usage.get("total_tokens")

        if new_tokens is not None:
            # ADK usually sends the running total, so we take the max to be safe
            total_tokens = max(total_tokens, new_tokens)

    # 2. Extract Detailed Tool Calls
    new_calls = extract_tool_calls_info(chunk)
    if new_calls:
        tool_calls.extend(new_calls)

    return total_tokens, tool_calls


def _finalize_metrics(total_tokens: int, tool_calls: List[Dict[str, Any]]) -> None:
    """Final accumulation of metrics to log context."""
    # Update ADK stats
    adk_ctx = log_ctx.get_all().get("adk", {})
    adk_ctx["total_tokens"] = total_tokens
    adk_ctx["tool_calls_count"] = len(tool_calls)
    log_ctx.add("adk", adk_ctx)

    # Log detailed tool invocations if they exist
    if tool_calls:
        log_ctx.add("tools", {
            "calls": tool_calls,
            "count": len(tool_calls)
        })


def _capture_metrics(result: Any) -> None:
    """Captures metrics from a non-streaming ADK result."""
    # 1. Extract Tokens
    total_tokens = 0
    usage = None
    for attr in ["usage", "usage_metadata"]:
        usage = getattr(result, attr, None)
        if usage is None and isinstance(result, dict):
            usage = result.get(attr)
        if usage:
            break

    if usage:
        val = getattr(usage, "total_tokens", None)
        if val is None and isinstance(usage, dict):
            val = usage.get("total_tokens")
        if val is not None:
            total_tokens = val

    # 2. Extract Tool Calls
    tool_calls = extract_tool_calls_info(result)

    # 3. Finalize
    _finalize_metrics(total_tokens, tool_calls)