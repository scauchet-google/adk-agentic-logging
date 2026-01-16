from typing import Any


def default_serializer(obj: Any) -> str:
    """
    Default serializer for JSON serialization to ensure robustness.
    Handles objects with isoformat() (like datetime) and falls back to str().
    """
    if hasattr(obj, "isoformat"):
        return str(obj.isoformat())
    return str(obj)
