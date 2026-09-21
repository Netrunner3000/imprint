"""Public interface for the Creator agent."""

from .agent import (
    ACCOUNT_TYPES, KINDS, PROMO_CHANNELS, ConsentError, CreatorAgent,
    require_ready,
)

__all__ = [
    "ACCOUNT_TYPES", "KINDS", "PROMO_CHANNELS", "ConsentError",
    "CreatorAgent", "require_ready", "CreatorPanel",
]

def __getattr__(name):
    # Lazy panel import keeps this package Qt-free at import time for
    # consumers that only want the agent (tests, CLI tools).
    if name == "CreatorPanel":
        from .panel import CreatorPanel
        return CreatorPanel
    raise AttributeError(name)

