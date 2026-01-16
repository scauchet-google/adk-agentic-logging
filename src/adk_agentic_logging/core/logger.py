import logging

logger = logging.getLogger("adk.agentic")

# Ensure logs are visible by default if not configured elsewhere
# Users can override this by configuring the "adk.agentic" logger.
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
