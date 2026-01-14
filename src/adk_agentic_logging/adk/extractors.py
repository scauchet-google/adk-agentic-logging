from typing import Any, Dict


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
