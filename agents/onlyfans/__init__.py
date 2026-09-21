"""OnlyFans workspace ownership boundary.

OnlyFans reuses Creator drafting while owning its analytics, consent and
venture-specific workflow.
"""

AGENT_KEY = "onlyfans"

from .trends import format_creator_brief

__all__ = ["AGENT_KEY", "OnlyFansDashboard", "format_creator_brief"]


def __getattr__(name):
    # Lazy panel import keeps this package Qt-free at import time, matching
    # the other panel-owning agent packages — the eager `from .panel import`
    # pulled PySide6 into every consumer that only wanted the trends helpers.
    if name == "OnlyFansDashboard":
        from .panel import OnlyFansDashboard
        return OnlyFansDashboard
    raise AttributeError(name)
