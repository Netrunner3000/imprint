"""The app's version, derived from the repository rather than hand-typed.

## The scheme

    v<MAJOR>.<BUILD>          e.g. v2.112

**MAJOR** is the product arc and the only hand-edited part. It lives in the
`VERSION` file at the project root and changes only on a deliberate milestone —
v1 was the Sentinel fork, v2 the rebuilt studio. Bumping it is a decision.

**BUILD** is `git rev-list --count HEAD`: the number of commits behind the
running code, zero-padded to three digits. It is not a decision and cannot be
forgotten, which is the point — a hand-maintained build number is wrong the
first time someone ships without remembering it, and then silently wrong
forever. Deriving it means the version *is* the development state.

It is monotonic on a linear history, which this repo has. A merge commit still
increments it, so the number never goes backwards; it is an ordering, not a
count of features.

## Why not semver

Semver's minor/patch split encodes a promise about API compatibility to
*other* software. Nothing imports Imprint, so that promise has no audience,
and inventing one would mean guessing every release whether a change was
"minor" or "patch" — a judgement with no consumer and therefore no right
answer. An arc plus a monotonic build says exactly what is true and nothing
more.

## Frozen builds

A `.app` has no `.git`, so the build number is stamped into
`_build_info.json` at package time by `scripts/stamp_version.py` and read back
here. Running from a checkout prefers live git, so an edit is reflected on the
next launch without re-stamping.

That difference is also what answers "am I running something current?" — see
`staleness()`. A frozen bundle carries the build it was made from; the checkout
knows the build it is at now. Comparing the two is the only honest way to say
whether the app someone just opened is up to date, and it is a question they
have actually asked.
"""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

from services.runtime_paths import is_frozen, resource_base

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Written at package time; read when there is no git to ask.
BUILD_INFO_NAME = "_build_info.json"

#: Width of the zero-padded build number. 3 keeps early builds reading as
#: versions ("v2.007") rather than as a draft.
BUILD_DIGITS = 3

FALLBACK_MAJOR = "2"


def _read_major() -> str:
    """The arc, from the VERSION file. Falls back rather than raising —
    a missing VERSION file should not stop the app opening."""
    for root in (PROJECT_ROOT, resource_base()):
        candidate = Path(root) / "VERSION"
        try:
            text = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text.lstrip("vV").split(".")[0]
    return FALLBACK_MAJOR


def _git(*args: str, cwd: Path | None = None) -> str | None:
    """Run git, or return None. Never raises: git may be absent, the directory
    may not be a repository, and neither is an error worth a traceback."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd or PROJECT_ROOT),
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _git_build(cwd: Path | None = None) -> dict | None:
    root = cwd or PROJECT_ROOT
    if not (root / ".git").exists():
        return None
    count = _git("rev-list", "--count", "HEAD", cwd=root)
    if not count or not count.isdigit():
        return None
    return {
        "build": int(count),
        "commit": _git("rev-parse", "--short", "HEAD", cwd=root) or "",
        "date": _git("log", "-1", "--format=%cI", cwd=root) or "",
        "source": "git",
    }


def _baked() -> dict | None:
    """The stamp written at package time, if there is one."""
    for root in (resource_base(), PROJECT_ROOT):
        try:
            data = json.loads((Path(root) / BUILD_INFO_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("build"), int):
            data.setdefault("source", "baked")
            return data
    return None


@lru_cache(maxsize=1)
def info() -> dict:
    """Everything known about the running build.

    Keys: major, build, version, commit, date, source. `source` is "git" when
    read live from the checkout, "baked" from a packaged stamp, "unknown" when
    neither is available — which is a real state (a source copy with no .git)
    and is shown as such rather than guessed at.
    """
    major = _read_major()
    # Frozen first asks its stamp: a bundle's own build is what it is running,
    # even when a checkout happens to sit beside it.
    found = (_baked() or _git_build()) if is_frozen() else (_git_build() or _baked())
    if not found:
        return {"major": major, "build": None, "version": f"v{major}.???",
                "commit": "", "date": "", "source": "unknown"}
    return {
        "major": major,
        "build": found["build"],
        "version": f"v{major}.{found['build']:0{BUILD_DIGITS}d}",
        "commit": found.get("commit", ""),
        "date": found.get("date", ""),
        "source": found.get("source", "unknown"),
    }


def version_string() -> str:
    """Just the badge text, e.g. "v2.112"."""
    return info()["version"]


def staleness() -> dict:
    """Whether what is running matches the checkout it came from.

    Returns `{"known": bool, "behind": int, "current": bool, "detail": str}`.
    `known` is False when there is nothing to compare against — no checkout, or
    no git — and the caller must say so rather than claiming "up to date",
    which is the failure this exists to avoid.
    """
    running = info()
    if running["build"] is None:
        return {"known": False, "behind": 0, "current": False,
                "detail": "This build carries no version stamp."}

    latest = _git_build()
    if latest is None:
        return {"known": False, "behind": 0, "current": False,
                "detail": "No checkout to compare against, so whether a newer "
                          "build exists cannot be known from here."}

    behind = latest["build"] - running["build"]
    if behind <= 0:
        return {"known": True, "behind": 0, "current": True,
                "detail": "Up to date with the checkout."}
    return {
        "known": True, "behind": behind, "current": False,
        "detail": (f"{behind} commit{'s' if behind != 1 else ''} behind the "
                   f"checkout (v{running['major']}.{latest['build']:0{BUILD_DIGITS}d}). "
                   "Re-run scripts/install_app.sh to catch up."),
    }


def tooltip() -> str:
    """The badge's hover text: what is running, and whether it is current."""
    running = info()
    lines = [f"Imprint {running['version']}"]
    if running["commit"]:
        lines.append(f"commit {running['commit']}")
    if running["date"]:
        lines.append(running["date"][:10])
    lines.append({"git": "running from the checkout",
                  "baked": "packaged build",
                  "unknown": "no version stamp"}[running["source"]])
    lines.append(staleness()["detail"])
    return "\n".join(lines)
