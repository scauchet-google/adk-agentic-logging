import functools
import inspect
from typing import (
    Any,
    AsyncGenerator,
    AsyncIterable,
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    Optional,
    Set,
    TypeVar,
    cast,
)

import opentelemetry.trace as trace

from adk_agentic_logging.adk.extractors import (
    extract_adk_metadata,
    extract_agent_config,
    extract_tool_calls_info,
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
        tracer = trace.get_tracer(__name__)
        span = tracer.start_span(f"ADK {func.__name__}")
        with trace.use_span(span, end_on_exit=False):
            _prepare_log_ctx(*args, **kwargs)
            try:
                result = await func(*args, **kwargs)

                # Handle streaming response
                if inspect.isasyncgen(result) or isinstance(result, AsyncIterable):
                    return _wrap_async_generator(result, span)

                # Handle direct response
                _capture_metrics(result)
                _add_span_attributes_from_ctx(span)
                span.end()
                return result
            except Exception as e:
                log_ctx.record_exception(e)
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                span.end()
                raise e

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        tracer = trace.get_tracer(__name__)
        span = tracer.start_span(f"ADK {func.__name__}")
        with trace.use_span(span, end_on_exit=False):
            _prepare_log_ctx(*args, **kwargs)
            try:
                result = func(*args, **kwargs)

                # Handle streaming response
                if inspect.isgenerator(result):
                    return _wrap_generator(result, span)

                if inspect.isasyncgen(result) or isinstance(result, AsyncIterable):
                    return _wrap_async_generator(result, span)

                # Handle direct response
                _capture_metrics(result)
                _add_span_attributes_from_ctx(span)
                span.end()
                return result
            except Exception as e:
                log_ctx.record_exception(e)
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                span.end()
                raise e

    if inspect.isasyncgenfunction(func):

        @functools.wraps(func)
        def async_gen_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = trace.get_tracer(__name__)
            # For async generators, we start a span that is closed when
            # the generator is exhausted
            span = tracer.start_span(f"ADK {func.__name__}")
            _prepare_log_ctx(*args, **kwargs)
            return _wrap_async_generator(func(*args, **kwargs), span)

        return cast(F, async_gen_wrapper)

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
    
    # Ensure temperature is in adk block if it was found in agent_config
    if "gen_ai" in log_ctx.get_all() and "temperature" in log_ctx.get_all()["gen_ai"]:
        if "temperature" not in adk_meta:
            adk_meta["temperature"] = log_ctx.get_all()["gen_ai"]["temperature"]

    log_ctx.add("adk", adk_meta)


def _wrap_generator(
    gen: Iterable[Any], span: Optional[trace.Span] = None
) -> Generator[Any, None, None]:
    """Wraps an ADK response generator to accumulate metrics."""
    total_tokens = 0
    tool_calls: List[Dict[str, Any]] = []
    agents_invoked: Set[str] = set()

    try:
        for chunk in gen:
            total_tokens, tool_calls, agents_invoked = _process_chunk(
                chunk, total_tokens, tool_calls, agents_invoked
            )
            yield chunk
    finally:
        _finalize_metrics(total_tokens, tool_calls, agents_invoked)
        if span:
            _add_span_attributes_from_ctx(span)
            span.end()


async def _wrap_async_generator(
    gen: AsyncIterable[Any], span: Optional[trace.Span] = None
) -> AsyncGenerator[Any, None]:
    """Wraps an ADK response async generator to accumulate metrics."""
    total_tokens = 0
    tool_calls: List[Dict[str, Any]] = []
    agents_invoked: Set[str] = set()

    try:
        async for chunk in gen:
            total_tokens, tool_calls, agents_invoked = _process_chunk(
                chunk, total_tokens, tool_calls, agents_invoked
            )
            yield chunk
    finally:
        _finalize_metrics(total_tokens, tool_calls, agents_invoked)
        if span:
            _add_span_attributes_from_ctx(span)
            span.end()


def _add_span_attributes_from_ctx(span: trace.Span) -> None:
    """Helper to add all current context to a span."""
    for key, val in log_ctx.get_all().items():
        if isinstance(val, dict):
            for k, v in val.items():
                attr_val = str(v)
                if len(attr_val) > 1024:
                    attr_val = attr_val[:1024] + "... [truncated]"
                span.set_attribute(f"{key}.{k}", attr_val)
        else:
            attr_val = str(val)
            if len(attr_val) > 1024:
                attr_val = attr_val[:1024] + "... [truncated]"
            span.set_attribute(key, attr_val)


def _process_chunk(
    chunk: Any,
    total_tokens: int,
    tool_calls: List[Dict[str, Any]],
    agents_invoked: Set[str],
) -> tuple[int, List[Dict[str, Any]], Set[str]]:
    """Extracts metrics from a single chunk."""

    # 1. Attempt to identify active agent in this chunk
    # ADK events might have 'agent_name' or 'source' attributes
    agent_name = getattr(chunk, "agent_name", getattr(chunk, "source", None))
    if agent_name and isinstance(agent_name, str):
        agents_invoked.add(agent_name)

    # 2. Extract Token Usage
    # Support both 'usage' and 'usage_metadata'
    usage = None
    for attr in ["usage", "usage_metadata"]:
        usage = getattr(chunk, attr, None)
        if usage is None and isinstance(chunk, dict):
            usage = chunk.get(attr)
        if usage:
            break

    if usage:
        # Support total_tokens and total_token_count (google-genai)
        new_tokens = getattr(
            usage, "total_tokens", getattr(usage, "total_token_count", None)
        )
        if new_tokens is None and isinstance(usage, dict):
            new_tokens = usage.get("total_tokens") or usage.get("total_token_count")

        if new_tokens is not None:
            # ADK usually sends the running total, take max to be safe
            total_tokens = max(total_tokens, new_tokens)

    # 3. Extract Detailed Tool Calls
    new_calls = extract_tool_calls_info(chunk)
    if new_calls:
        tool_calls.extend(new_calls)

    return total_tokens, tool_calls, agents_invoked


def _finalize_metrics(
    total_tokens: int, tool_calls: List[Dict[str, Any]], agents_invoked: Set[str]
) -> None:
    """Final accumulation of metrics to log context."""
    # Update ADK stats
    adk_ctx = log_ctx.get_all().get("adk", {})
    adk_ctx["total_tokens"] = total_tokens
    adk_ctx["tool_calls_count"] = len(tool_calls)

    if agents_invoked:
        adk_ctx["agents_invoked"] = list(agents_invoked)

    log_ctx.add("adk", adk_ctx)

    # Log detailed tool invocations if they exist
    if tool_calls:
        log_ctx.add("tools", {"calls": tool_calls, "count": len(tool_calls)})


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
        val = getattr(usage, "total_tokens", getattr(usage, "total_token_count", None))
        if val is None and isinstance(usage, dict):
            val = usage.get("total_tokens") or usage.get("total_token_count")
        if val is not None:
            total_tokens = val

    # 2. Extract Tool Calls
    tool_calls = extract_tool_calls_info(result)

    # 3. Agents Invoked (Best effort)
    agents_invoked = set()
    agent_name = getattr(result, "agent_name", getattr(result, "source", None))
    if agent_name and isinstance(agent_name, str):
        agents_invoked.add(agent_name)

    # 4. Finalize
    _finalize_metrics(total_tokens, tool_calls, agents_invoked)
