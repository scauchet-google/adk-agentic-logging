from adk_agentic_logging import log_ctx


def test_top_level_import() -> None:
    """Verify log_ctx can be imported from the top level."""
    assert log_ctx is not None

def test_enrich_method() -> None:
    """Verify the enrichment method adds multiple attributes."""
    log_ctx.clear()
    log_ctx.enrich(question="test question", response="test response", other=123)
    
    ctx = log_ctx.get_all()
    assert ctx["question"] == "test question"
    assert ctx["response"] == "test response"
    assert ctx["other"] == 123

def test_enrich_idempotency() -> None:
    """Verify enrichment merges with existing data."""
    log_ctx.clear()
    log_ctx.add("initial", "val")
    log_ctx.enrich(enriched="new")
    
    ctx = log_ctx.get_all()
    assert ctx["initial"] == "val"
    assert ctx["enriched"] == "new"
