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
            _prepare_log_ctx(func, *args, **kwargs)
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
            _prepare_log_ctx(func, *args, **kwargs)
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
            _prepare_log_ctx(func, *args, **kwargs)
            return _wrap_async_generator(func(*args, **kwargs), span)

        return cast(F, async_gen_wrapper)

    if inspect.iscoroutinefunction(func):
        return cast(F, async_wrapper)
    return cast(F, sync_wrapper)


def _prepare_log_ctx(func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Extracts metadata from input and adds it to the log context."""
    sig = inspect.signature(func)
    bound = sig.bind_partial(*args, **kwargs)

    # 1. Extract Agent Configuration from the runner instance (self)
    runner_instance = bound.arguments.get("self") or bound.arguments.get("cls")
    if not runner_instance and args:
        # Fallback to first arg if not bound by name
        runner_instance = args[0]

    if runner_instance:
        agent_config = extract_agent_config(runner_instance)
        if agent_config:
            # Map to gen_ai namespace
            gen_ai = {
                "agent": {"name": agent_config.get("agent_name", "unknown_agent")},
                "model": agent_config.get("model", "unknown_model"),
            }
            # Add other model params
            for k in ["temperature", "top_k", "top_p", "max_output_tokens"]:
                if k in agent_config:
                    gen_ai[k] = agent_config[k]
            log_ctx.add("gen_ai", gen_ai)

    # 2. Extract Input Metadata (session_id, user_id, etc.)
    # Look for typical ADK argument names like 'input', 'runner_input', 'messages'
    input_obj = (
        bound.arguments.get("runner_input")
        or bound.arguments.get("input")
        or bound.arguments.get("messages")
    )

    # Fallback logic if not found by name
    if not input_obj:
        if len(args) > 1:
            input_obj = args[1]
        elif kwargs:
            input_obj = kwargs

    adk_meta = extract_adk_metadata(input_obj)

    # Map to app namespace
    app_ctx = {}
    if "user_id" in adk_meta:
        app_ctx["user_id"] = adk_meta.pop("user_id")
    if "session_id" in adk_meta:
        app_ctx["session_id"] = adk_meta.pop("session_id")
    if "tenant_id" in adk_meta:
        app_ctx["tenant_id"] = adk_meta.pop("tenant_id")

    if app_ctx:
        log_ctx.add("app", app_ctx)

    # Extract prompt for snippet strategy
    prompt = None
    if isinstance(input_obj, dict):
        prompt = input_obj.get("message") or input_obj.get("prompt")
    elif input_obj:
        prompt = getattr(input_obj, "message", getattr(input_obj, "prompt", None))

    if prompt:
        log_ctx.add_content("gen_ai.content.prompt", str(prompt))

    # Remaining adk meta (like temperature override)
    if adk_meta:
        # If temperature is in adk_meta, ensure it's also in gen_ai if not already
        if "temperature" in adk_meta:
            gen_ai = log_ctx.get_all().get("gen_ai", {})
            gen_ai["temperature"] = adk_meta["temperature"]
            log_ctx.add("gen_ai", gen_ai)

        # We still keep 'adk' for internal/other fields if any
        log_ctx.add("adk", adk_meta)


def _wrap_generator(
    gen: Iterable[Any], span: Optional[trace.Span] = None
) -> Generator[Any, None, None]:
    """Wraps an ADK response generator to accumulate metrics."""
    total_tokens = 0
    tool_calls: List[Dict[str, Any]] = []
    agents_invoked: Set[str] = set()
    completion_text = []

    try:
        for chunk in gen:
            total_tokens, tool_calls, agents_invoked = _process_chunk(
                chunk, total_tokens, tool_calls, agents_invoked
            )
            # Accumulate completion text
            text = getattr(chunk, "text", None)
            if text is None and isinstance(chunk, dict):
                text = chunk.get("text")
            if text:
                completion_text.append(str(text))
            yield chunk
    finally:
        if completion_text:
            log_ctx.add_content("gen_ai.content.completion", "".join(completion_text))

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
    completion_text = []

    try:
        async for chunk in gen:
            total_tokens, tool_calls, agents_invoked = _process_chunk(
                chunk, total_tokens, tool_calls, agents_invoked
            )
            # Accumulate completion text
            text = getattr(chunk, "text", None)
            if text is None and isinstance(chunk, dict):
                text = chunk.get("text")
            if text:
                completion_text.append(str(text))
            yield chunk
    finally:
        if completion_text:
            log_ctx.add_content("gen_ai.content.completion", "".join(completion_text))

        _finalize_metrics(total_tokens, tool_calls, agents_invoked)
        if span:
            _add_span_attributes_from_ctx(span)
            span.end()


def _add_span_attributes_from_ctx(span: trace.Span) -> None:
    """Helper to add all current context to a span."""

    def _set_nested_attr(prefix: str, data: Any) -> None:
        if isinstance(data, dict):
            for k, v in data.items():
                _set_nested_attr(f"{prefix}.{k}" if prefix else k, v)
        else:
            attr_val = str(data)
            # Snippet strategy is handled by add_content,
            # but we still guard against massive fields here.
            if len(attr_val) > 1024:
                attr_val = attr_val[:1024] + "... [truncated]"
            span.set_attribute(prefix, attr_val)

    for key, val in log_ctx.get_all().items():
        # Skip special logging keys
        if key in ["severity", "timestamp", "message"]:
            continue
        _set_nested_attr(key, val)


def _process_chunk(
    chunk: Any,
    total_tokens: int,
    tool_calls: List[Dict[str, Any]],
    agents_invoked: Set[str],
) -> tuple[int, List[Dict[str, Any]], Set[str]]:
    """Extracts metrics from a single chunk."""

    # 1. Attempt to identify active agent in this chunk
    agent_name = getattr(chunk, "agent_name", getattr(chunk, "source", None))
    if agent_name and isinstance(agent_name, str):
        agents_invoked.add(agent_name)

    # 2. Extract Token Usage
    usage = None
    for attr in ["usage", "usage_metadata"]:
        usage = getattr(chunk, attr, None)
        if usage is None and isinstance(chunk, dict):
            usage = chunk.get(attr)
        if usage:
            break

    if usage:
        # Extract individual token counts
        input_tokens = getattr(
            usage, "prompt_tokens", getattr(usage, "prompt_token_count", None)
        )
        output_tokens = getattr(
            usage,
            "completion_tokens",
            getattr(usage, "candidates_token_count", None),
        )
        total_tokens_val = getattr(
            usage, "total_tokens", getattr(usage, "total_token_count", None)
        )

        if isinstance(usage, dict):
            input_tokens = (
                input_tokens
                or usage.get("prompt_tokens")
                or usage.get("prompt_token_count")
            )
            output_tokens = (
                output_tokens
                or usage.get("completion_tokens")
                or usage.get("candidates_token_count")
            )
            total_tokens_val = (
                total_tokens_val
                or usage.get("total_tokens")
                or usage.get("total_token_count")
            )

        if total_tokens_val:
            total_tokens = max(total_tokens, total_tokens_val)

        # We store input/output tokens if they are cumulative or if they are
        # the last ones.
        # For simplicity, we just add them to the gen_ai.usage context
        # if they exist.
        gen_ai = log_ctx.get_all().get("gen_ai", {})
        usage_ctx = gen_ai.get("usage", {})
        if input_tokens:
            usage_ctx["input_tokens"] = input_tokens
        if output_tokens:
            usage_ctx["output_tokens"] = output_tokens
        if usage_ctx:
            gen_ai["usage"] = usage_ctx
            log_ctx.add("gen_ai", gen_ai)

    # 3. Extract Detailed Tool Calls
    new_calls = extract_tool_calls_info(chunk)
    if new_calls:
        tool_calls.extend(new_calls)

    return total_tokens, tool_calls, agents_invoked


def _finalize_metrics(
    total_tokens: int, tool_calls: List[Dict[str, Any]], agents_invoked: Set[str]
) -> None:
    """Final accumulation of metrics to log context."""
    # Update GenAI usage
    gen_ai = log_ctx.get_all().get("gen_ai", {})
    usage = gen_ai.get("usage", {})
    usage["total_tokens"] = total_tokens
    gen_ai["usage"] = usage

    if agents_invoked:
        agent = gen_ai.get("agent", {})
        agent["invoked"] = list(agents_invoked)
        gen_ai["agent"] = agent

    log_ctx.add("gen_ai", gen_ai)

    # Log detailed tool invocations
    if tool_calls:
        log_ctx.add("tools", {"calls": tool_calls, "count": len(tool_calls)})


def _capture_metrics(result: Any) -> None:
    """Captures metrics from a non-streaming ADK result."""
    # 1. Extract Tokens
    total_tokens = 0
    input_tokens = None
    output_tokens = None

    usage = None
    for attr in ["usage", "usage_metadata"]:
        usage = getattr(result, attr, None)
        if usage is None and isinstance(result, dict):
            usage = result.get(attr)
        if usage:
            break

    if usage:
        input_tokens = getattr(
            usage, "prompt_tokens", getattr(usage, "prompt_token_count", None)
        )
        output_tokens = getattr(
            usage,
            "completion_tokens",
            getattr(usage, "candidates_token_count", None),
        )
        total_tokens_val = getattr(
            usage, "total_tokens", getattr(usage, "total_token_count", None)
        )

        if isinstance(usage, dict):
            input_tokens = (
                input_tokens
                or usage.get("prompt_tokens")
                or usage.get("prompt_token_count")
            )
            output_tokens = (
                output_tokens
                or usage.get("completion_tokens")
                or usage.get("candidates_token_count")
            )
            total_tokens_val = (
                total_tokens_val
                or usage.get("total_tokens")
                or usage.get("total_token_count")
            )

        if total_tokens_val:
            total_tokens = total_tokens_val

    # 2. Extract Tool Calls
    tool_calls = extract_tool_calls_info(result)

    # 3. Agents Invoked (Best effort)
    agents_invoked = set()
    agent_name = getattr(result, "agent_name", getattr(result, "source", None))
    if agent_name and isinstance(agent_name, str):
        agents_invoked.add(agent_name)

    # 4. Finalize
    _finalize_metrics(total_tokens, tool_calls, agents_invoked)

    # Add input/output tokens to usage ctx if they were found
    if input_tokens or output_tokens:
        gen_ai = log_ctx.get_all().get("gen_ai", {})
        usage_ctx = gen_ai.get("usage", {})
        if input_tokens:
            usage_ctx["input_tokens"] = input_tokens
        if output_tokens:
            usage_ctx["output_tokens"] = output_tokens
        gen_ai["usage"] = usage_ctx
        log_ctx.add("gen_ai", gen_ai)
