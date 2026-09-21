"""Public interface for the Book Author agent."""

from .agent import AuthorAgent

__all__ = ["AuthorAgent", "AuthorPanel"]


def __getattr__(name):
    # Lazy panel import keeps this package Qt-free at import time for
    # consumers that only want the agent (tests, CLI tools).
    if name == "AuthorPanel":
        from .panel import AuthorPanel
        return AuthorPanel
    raise AttributeError(name)
