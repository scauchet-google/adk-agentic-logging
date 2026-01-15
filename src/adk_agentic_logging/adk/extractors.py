from typing import Any, Dict, List


def extract_adk_metadata(runner_input: Any) -> Dict[str, Any]:
    """
    Defensive metadata extraction from ADK runner input using duck-typing.
    Avoids direct dependency on ADK classes.
    """
    metadata = {}

    # Common ADK fields
    for field in ["session_id", "user_id", "tenant_id", "conversation_id"]:
        # Check direct attributes
        val = getattr(runner_input, field, None)
        if val:
            metadata[field] = val

        # Check dictionary-like access if available
        elif isinstance(runner_input, dict):
            val = runner_input.get(field)
            if val:
                metadata[field] = val

    # Also look into nested objects if they exist
    # e.g., runner_input.context.session_id
    context = getattr(runner_input, "context", None)
    if context:
        for field in ["session_id", "user_id", "tenant_id", "conversation_id"]:
            val = getattr(context, field, None)
            if val and field not in metadata:
                metadata[field] = val

    return metadata


def extract_agent_config(runner_instance: Any) -> Dict[str, Any]:
    """
    Extracts static configuration from the Runner's agent instance.
    Captures Model Name, Temperature, and Agent Name.
    """
    config: Dict[str, Any] = {}

    # Typically runner.agent holds the root agent
    agent = getattr(runner_instance, "agent", None)
    if not agent:
        return config

    config["agent_name"] = getattr(agent, "name", "unknown_agent")

    # Extract Model Config
    model = getattr(agent, "model", None)
    if model:
        # Model can be a string or a configured object (e.g., Gemini(...))
        if isinstance(model, str):
            config["model"] = model
        else:
            # Try common attribute names for model objects
            config["model"] = getattr(
                model, "model_name", getattr(model, "model", "unknown_model")
            )

            # Extract generation config (temperature, etc.)
            for param in ["temperature", "top_k", "top_p", "max_output_tokens"]:
                val = getattr(model, param, None)
                if val is not None:
                    config[param] = val

    return config


def extract_tool_calls_info(chunk_or_result: Any) -> List[Dict[str, Any]]:
    """
    Extracts a list of tool calls with names and arguments.
    Supports:
    1. Direct 'tool_calls' attribute (legacy/mocks)
    2. 'content.parts' with 'function_call' (Latest ADK / google-genai)
    """
    details = []

    # 1. Try legacy 'tool_calls' attribute
    tool_calls = getattr(chunk_or_result, "tool_calls", None)
    if tool_calls is None and isinstance(chunk_or_result, dict):
        tool_calls = chunk_or_result.get("tool_calls")

    if tool_calls and isinstance(tool_calls, (list, tuple)):
        for call in tool_calls:
            func = getattr(call, "function", None)
            if func is None and isinstance(call, dict):
                func = call.get("function")

            if func:
                name = getattr(func, "name", None)
                if name is None and isinstance(func, dict):
                    name = func.get("name")

                args = getattr(func, "arguments", getattr(func, "args", None))
                if args is None and isinstance(func, dict):
                    args = func.get("arguments") or func.get("args")

                if name:
                    details.append({"name": name, "arguments": args or {}})

    # 2. Try latest ADK 'content.parts'
    content = getattr(chunk_or_result, "content", None)
    if content is None and isinstance(chunk_or_result, dict):
        content = chunk_or_result.get("content")

    if content:
        parts = getattr(content, "parts", None)
        if parts is None and isinstance(content, dict):
            parts = content.get("parts")

        if parts and isinstance(parts, (list, tuple)):
            for part in parts:
                fcall = getattr(part, "function_call", None)
                if fcall is None and isinstance(part, dict):
                    fcall = part.get("function_call")

                if fcall:
                    name = getattr(fcall, "name", None)
                    if name is None and isinstance(fcall, dict):
                        name = fcall.get("name")

                    # google-genai uses 'args', some other versions use 'arguments'
                    args = getattr(fcall, "args", getattr(fcall, "arguments", None))
                    if args is None and isinstance(fcall, dict):
                        args = fcall.get("args") or fcall.get("arguments")

                    if name:
                        details.append({"name": name, "arguments": args or {}})

    return details
