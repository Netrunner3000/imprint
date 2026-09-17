"""Public interface for the Site Builder agent."""

from .agent import WebdesignAgent

__all__ = ["WebdesignAgent", "WebdesignPanel"]


def __getattr__(name):
    # Domain/CLI imports should not initialize Qt until the GUI needs it.
    if name == "WebdesignPanel":
        from .panel import WebdesignPanel
        return WebdesignPanel
    raise AttributeError(name)
