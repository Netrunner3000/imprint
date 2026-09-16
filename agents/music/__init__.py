"""Public interface for the Music agent."""

from .agent import MusicAgent

__all__ = ["MusicAgent", "MusicPanel"]


def __getattr__(name):
    # Keep CLI/domain imports free of Qt until the GUI actually asks for it.
    if name == "MusicPanel":
        from .panel import MusicPanel
        return MusicPanel
    raise AttributeError(name)
