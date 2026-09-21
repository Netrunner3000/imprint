"""Public interface for the Social agent."""

from .agent import (
    ANGLES, SUBJECT_KINDS, build_clip_brief_messages, build_post_messages,
    over_limit, split_variants,
)

__all__ = [
    "ANGLES", "SUBJECT_KINDS", "build_clip_brief_messages",
    "build_post_messages", "over_limit", "split_variants", "SocialPanel",
]


def __getattr__(name):
    # Lazy panel import keeps this package Qt-free at import time for
    # consumers that only want the prompt builders (tests, CLI tools).
    if name == "SocialPanel":
        from .panel import SocialPanel
        return SocialPanel
    raise AttributeError(name)
