#!/usr/bin/env python3
"""Freeze the current build number into `_build_info.json`.

A packaged `.app` has no `.git`, so it cannot derive its own version at
runtime. Both install paths call this first, which is what lets a bundle say
which build it is — and, by comparison with the checkout, whether it is still
the current one.

Run by `scripts/build_app.sh` and `scripts/install_app.sh`; safe to run by
hand. Writes nothing and exits 0 when git is unavailable: a missing stamp
degrades to "no version stamp" in the UI, which is honest, whereas a guessed
number would not be.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.version import BUILD_INFO_NAME, _git_build, _read_major  # noqa: E402


def main() -> int:
    found = _git_build(PROJECT_ROOT)
    if not found:
        print("stamp_version: no git metadata available — leaving the build "
              "unstamped rather than inventing a number.", file=sys.stderr)
        return 0

    major = _read_major()
    payload = {
        "major": major,
        "build": found["build"],
        "commit": found["commit"],
        "date": found["date"],
        "source": "baked",
    }
    target = PROJECT_ROOT / BUILD_INFO_NAME
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"stamped v{major}.{found['build']:03d} ({found['commit']}) -> "
          f"{target.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
