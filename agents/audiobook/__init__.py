"""Public interface for the Audiobook agent."""

from .agent import AudiobookConnector

__all__ = ["AudiobookConnector", "AudiobookPanel"]


def __getattr__(name):
    # Keep converter/CLI imports Qt-free until the desktop view is requested.
    if name == "AudiobookPanel":
        from .panel import AudiobookPanel
        return AudiobookPanel
    raise AttributeError(name)
