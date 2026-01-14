import functools
import inspect
from typing import Any, Callable, Generator, Iterable, TypeVar, cast

from adk_agentic_logging.adk.extractors import extract_adk_metadata
from adk_agentic_logging.core.context import log_ctx

F = TypeVar("F", bound=Callable[..., Any])


def instrument_runner(func: F) -> F:
    """
    Decorator for ADK Runner.run method.
    Captures session/user IDs and wraps generators for metric accumulation.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Extract metadata from input
        # Usually first arg after self or named kwargs
        input_obj = args[1] if len(args) > 1 else kwargs.get("runner_input")
        if not input_obj and kwargs:
            input_obj = kwargs

        adk_meta = extract_adk_metadata(input_obj)
        log_ctx.add("adk", adk_meta)

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

    return cast(F, wrapper)


def _wrap_generator(gen: Iterable[Any]) -> Generator[Any, None, None]:
    """Wraps an ADK response generator to accumulate metrics."""
    total_tokens = 0
    tool_calls = []

    try:
        for chunk in gen:
            # Extract metrics from chunk (ADK convention: chunk.usage.total_tokens etc.)
            usage = getattr(chunk, "usage", None)
            if usage:
                total_tokens = getattr(usage, "total_tokens", total_tokens)

            # Extract tool calls
            calls = getattr(chunk, "tool_calls", None)
            if calls:
                tool_calls.extend(calls)

            yield chunk
    finally:
        # Final accumulation to log context
        adk_ctx = log_ctx.get_all().get("adk", {})
        adk_ctx["total_tokens"] = total_tokens
        if tool_calls:
            adk_ctx["tool_calls_count"] = len(tool_calls)
        log_ctx.add("adk", adk_ctx)


def _capture_metrics(result: Any) -> None:
    """Captures metrics from a non-streaming ADK result."""
    usage = getattr(result, "usage", None)
    if usage:
        adk_ctx = log_ctx.get_all().get("adk", {})
        adk_ctx["total_tokens"] = getattr(usage, "total_tokens", 0)
        log_ctx.add("adk", adk_ctx)
