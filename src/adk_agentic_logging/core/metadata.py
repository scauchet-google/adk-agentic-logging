import os
import urllib.request
from typing import Optional, cast


def get_google_project_id() -> Optional[str]:
    """
    Detects the GCP Project ID without requiring environment variables.
    Resolution order:
    1. GOOGLE_CLOUD_PROJECT env var
    2. GCP Metadata Server
    3. Fallback to None
    """
    # 1. Check Env
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project_id:
        return project_id

    # 2. Check Metadata Server (Short timeout for non-GCP environments)
    try:
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=0.1) as response:
            return cast(str, response.read().decode("utf-8"))
    except Exception:
        # Not on GCP or server unreachable
        return None
