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
    config = {}
    
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
            config["model"] = getattr(model, "model_name", getattr(model, "model", "unknown_model"))
            
            # Extract generation config (temperature, etc.)
            # These might be direct attributes or in a config object (generation_config)
            params = ["temperature", "top_k", "top_p", "max_output_tokens"]
            for param in params:
                val = getattr(model, param, None)
                if val is not None:
                    config[param] = val
            
            # If not found directly, check generation_config
            gen_config = getattr(model, "generation_config", None)
            if gen_config:
                for param in params:
                    if param not in config:
                        # Check attribute
                        val = getattr(gen_config, param, None)
                        if val is None and isinstance(gen_config, dict):
                            # Check dict
                            val = gen_config.get(param)
                        if val is not None:
                            config[param] = val

    return config


def extract_tool_calls_info(chunk_or_result: Any) -> List[Dict[str, Any]]:
    """
    Extracts a list of tool calls with names and arguments.
    Supports both attribute access (objects) and dictionary access.
    """
    details = []
    
    # 1. Try attribute access
    tool_calls = getattr(chunk_or_result, "tool_calls", None)
    # 2. Try dict access
    if tool_calls is None and isinstance(chunk_or_result, dict):
        tool_calls = chunk_or_result.get("tool_calls")
        
    if not tool_calls or not isinstance(tool_calls, (list, tuple)):
        return details

    for call in tool_calls:
        func = getattr(call, "function", None)
        if func is None and isinstance(call, dict):
            func = call.get("function")
            
        if func:
            name = getattr(func, "name", None)
            if name is None and isinstance(func, dict):
                name = func.get("name")
                
            args = getattr(func, "arguments", None)
            if args is None and isinstance(func, dict):
                args = func.get("arguments")
                
            if name:
                details.append({
                    "name": name,
                    "arguments": args or {}
                })
            
    return details