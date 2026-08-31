"""Opt-in protocol dispatch outside the frozen legacy agent implementation."""

from . import agent as legacy_agent


def _decorate_legacy(episode):
    """Give callers one result surface without editing sealed legacy code."""
    episode.terminal_status = "completed" if episode.finished else "incomplete"
    episode.completion = None
    episode.runtime_protocol = "legacy"
    episode.lifecycle_path = None
    episode.ledger = None
    return episode


def run(llm, task_text, attempt):
    protocol = attempt.config.runtime_protocol
    if protocol == "receipt_v1":
        if attempt.config.condition != "harness":
            raise ValueError("receipt_v1 requires the harness condition")
        from .managed_agent import run_receipt_v1

        return run_receipt_v1(llm, task_text, attempt)
    if protocol != "legacy":
        raise ValueError("unsupported runtime protocol {!r}".format(protocol))
    return _decorate_legacy(legacy_agent.run(llm, task_text, attempt))


__all__ = ["run"]
