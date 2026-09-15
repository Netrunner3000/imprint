"""Video workspace ownership boundary.

The pipeline remains the separately versioned ``vidforge`` companion.  Imprint
owns its Vidforge adapter in ``agents.video.studio`` while the umbrella shell
still owns the shared panel layout.
"""

AGENT_KEY = "video"

from . import studio as video_studio

__all__ = ["AGENT_KEY", "video_studio"]
