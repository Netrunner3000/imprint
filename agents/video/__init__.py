"""Video workspace ownership boundary.

The pipeline remains the separately versioned ``vidforge`` companion.  Imprint
owns its Vidforge adapter in ``agents.video.studio`` while the umbrella shell
still owns the shared panel layout.
"""

AGENT_KEY = "video"

from . import studio as video_studio

__all__ = ["AGENT_KEY", "video_studio", "VideoPanel"]


def __getattr__(name):
    # Lazy panel import keeps this package Qt-free at import time for
    # consumers that only want the studio adapter (tests, CLI tools).
    if name == "VideoPanel":
        from .panel import VideoPanel
        return VideoPanel
    raise AttributeError(name)
