"""OnlyFans workspace ownership boundary.

OnlyFans reuses Creator drafting while owning its analytics, consent and
venture-specific workflow.
"""

AGENT_KEY = "onlyfans"

from .panel import OnlyFansDashboard
from .trends import format_creator_brief

__all__ = ["AGENT_KEY", "OnlyFansDashboard", "format_creator_brief"]
