"""Public interface for the Publishing Manager agent."""

from .agent import ManuscriptAgent

__all__ = ["ManuscriptAgent", "ManuscriptPanel", "ShortsWorker",
           "manuscript_seed_todos"]


def __getattr__(name):
    # Lazy panel import keeps this package Qt-free at import time for
    # consumers that only want the agent (tests, CLI tools).
    if name == "ManuscriptPanel":
        from .panel import ManuscriptPanel
        return ManuscriptPanel
    if name == "ShortsWorker":
        from .workers import ShortsWorker
        return ShortsWorker
    if name == "manuscript_seed_todos":
        from .kdp_csv_parser import manuscript_seed_todos
        return manuscript_seed_todos
    raise AttributeError(name)
