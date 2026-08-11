"""
Helpers for parsing structured data out of LLM responses.

Models are asked for clean JSON but don't always comply — they wrap it in
markdown fences, add a sentence of preamble, or fall back to a bulleted list.
These helpers degrade gracefully through those cases rather than failing outright.
"""

from __future__ import annotations
import json
import re


def parse_string_list(text: str) -> list[str]:
    """Parse an LLM response into a list of strings.

    Tries, in order: raw JSON → JSON array embedded in surrounding prose →
    line-by-line fallback (stripping bullets, numbering, and quote marks).
    Always returns a list; an unparseable response yields its non-empty lines.
    """
    text = text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(q).strip() for q in data if str(q).strip()]
    except Exception:
        pass

    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                return [str(q).strip() for q in data if str(q).strip()]
        except Exception:
            pass

    lines = []
    for line in text.splitlines():
        line = line.strip().strip("-•* ").strip()
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        line = line.strip("\"“”")
        if line:
            lines.append(line)
    return lines
