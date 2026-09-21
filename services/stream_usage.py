"""Carry provider usage across a streamed response.

A generator can only yield text, but the provider's real token counts arrive
in its final frame (OpenAI-compatible `stream_options={"include_usage"}`
chunk, Anthropic's final message, Gemini's usage_metadata). Before this
existed, every cloud stream discarded those counts and billing fell back to
the chars/4 estimate — and Kimi's cached-input billing could never fire.

Each client builds its token generator through a factory that receives the
UsageStream itself, fills `.usage` when the final frame arrives, and the
consumer (ui/workers.ChatWorker) reads `.usage` after draining the stream.
"""

from __future__ import annotations

from typing import Callable, Generator


class UsageStream:
    """Iterate the wrapped generator; expose the provider's final usage."""

    def __init__(self, make_gen: Callable[["UsageStream"], Generator]):
        self.usage: dict | None = None
        self._gen = make_gen(self)

    def __iter__(self):
        return self._gen


def cached_input_tokens(usage) -> int:
    """Input tokens the provider served from its prompt cache, or 0.

    Two shapes are in the wild on OpenAI-compatible endpoints, so both are
    read rather than assuming one: OpenAI nests it under
    `prompt_tokens_details.cached_tokens`, while the DeepSeek-style APIs report
    a flat `prompt_cache_hit_tokens`. Anything unrecognised counts as no cache
    hit, which bills at the full input rate — the conservative direction.
    """
    if not usage:
        return 0
    details = getattr(usage, "prompt_tokens_details", None)
    nested = getattr(details, "cached_tokens", None) if details else None
    if nested is None and isinstance(details, dict):
        nested = details.get("cached_tokens")
    flat = getattr(usage, "prompt_cache_hit_tokens", None)
    for value in (nested, flat):
        try:
            if value is not None:
                return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0
