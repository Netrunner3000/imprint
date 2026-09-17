"""Pure project-context helpers shared by the chat and agent workers."""

from __future__ import annotations


def with_project_instructions(messages: list[dict], instructions: str) -> list[dict]:
    """Return a copy with project context in one system message, exactly once."""
    clean = instructions.strip()
    copied = [dict(message) for message in messages]
    if not clean:
        return copied
    block = f"Project instructions:\n{clean}"
    for message in copied:
        if message.get("role") == "system":
            current = str(message.get("content") or "")
            if block not in current:
                message["content"] = f"{block}\n\n{current}" if current else block
            return copied
    return [{"role": "system", "content": block}, *copied]


def conversation_turns(messages: list[dict], response: str = "") -> list[dict]:
    """Recover user/assistant turns, including replies in older chat files."""
    turns = [dict(message) for message in messages
             if message.get("role") in {"user", "assistant"}]
    if response and (not turns or turns[-1].get("role") != "assistant"
                     or turns[-1].get("content") != response):
        turns.append({"role": "assistant", "content": response})
    return turns


def continue_chat_messages(fresh: list[dict], previous: list[dict]) -> list[dict]:
    """Use today's system context, followed by prior turns and the new request.

    Persisted system messages may contain instructions from a different project
    or an outdated tool. They are deliberately not reused.
    """
    system = [dict(message) for message in fresh if message.get("role") == "system"]
    current = [dict(message) for message in fresh if message.get("role") != "system"]
    return system + conversation_turns(previous) + current
