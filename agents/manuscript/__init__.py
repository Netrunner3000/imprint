"""Public interface for the Publishing Manager agent."""

from .agent import ManuscriptAgent

__all__ = ["ManuscriptAgent", "ManuscriptPanel"]


def __getattr__(name):
    # Lazy panel import keeps this package Qt-free at import time for
    # consumers that only want the agent (tests, CLI tools).
    if name == "ManuscriptPanel":
        from .panel import ManuscriptPanel
        return ManuscriptPanel
    raise AttributeError(name)
