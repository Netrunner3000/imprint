"""Public interface for the Client Gigs agent."""

from .agent import FiverrAgent

__all__ = ["FiverrAgent", "FiverrPanel"]


def __getattr__(name):
    # Keep domain-only imports free of Qt until the desktop asks for the panel.
    if name == "FiverrPanel":
        from .panel import FiverrPanel
        return FiverrPanel
    raise AttributeError(name)
