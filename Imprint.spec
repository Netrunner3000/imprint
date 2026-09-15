# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Imprint — self-contained macOS .app bundle.

Build:   .venv/bin/pyinstaller --noconfirm Imprint.spec
Output:  dist/Imprint.app
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = [
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    "services.narrator.converter",   # invoked via the --narrator-worker sentinel
    # vidforge is imported through agents/video/studio.py at runtime, so
    # static analysis of main.py never sees these.
    "vidforge",
    "vidforge.pipeline",
    "vidforge.progress",
    "vidforge.config",
    "vidforge.history",
    "vidforge.youtube",
]

# SDKs / libs with data files or plugin discovery that static analysis can miss.
for pkg in ("google.genai", "tiktoken", "anthropic", "openai", "certifi",
            "yaml", "googleapiclient", "google_auth_oauthlib"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# vidforge is a nested sibling repository, not a vendored copy — see
# agents/video/studio.py. The package ships as source so the same checkout
# drives both this bundle and the standalone vidforge.app.
_VIDFORGE = Path("vidforge")
if (_VIDFORGE / "vidforge").is_dir():
    datas += [(str(_VIDFORGE / "vidforge"), "vidforge")]
    # config.yaml and topics.txt are seeded into ~/Library/Application Support/
    # vidforge on first run, and its assets/ holds the music and fonts the
    # pipeline composites in. Frozen, vidforge resolves BUNDLE_ROOT to this
    # bundle's root, so they have to sit at the top level.
    for _name in ("config.yaml", "topics.txt"):
        if (_VIDFORGE / _name).is_file():
            datas += [(str(_VIDFORGE / _name), ".")]
    if (_VIDFORGE / "assets").is_dir():
        datas += [(str(_VIDFORGE / "assets"), "assets")]

# Read-only resources seeded into the writable user-data dir on first launch.
datas += [
    ("config", "config"),
    ("assets/dropdown-chevron.svg", "assets"),
    ("README.md", "."),
    (".env.example", "."),
    ("docs/agents", "docs/agents"),   # per-agent capability sheets (Docs button)
    ("docs/learn", "docs/learn"),     # Learning Centre pages + their screenshots
]

# Per-agent project documents are part of the product architecture, not dev-only
# notes.  Keep their directory identity so the packaged Docs fallback and
# self-test see the same ownership structure as a source checkout.
for _agent_project in Path("agents").iterdir():
    if not _agent_project.is_dir() or _agent_project.name.startswith((".", "__")):
        continue
    for _project_doc in ("README.md", "TODO.md", "SUGGESTIONS.md"):
        _source = _agent_project / _project_doc
        if _source.is_file():
            datas.append((str(_source), f"agents/{_agent_project.name}"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Not imported by main.py; pulls broken providers.avatar/voice imports.
        "agents.course.agent",
        # Dev-only weight.
        "pytest", "pip", "setuptools",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Imprint",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,             # windowed GUI app — no terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,          # native arch (arm64 on this Mac)
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Imprint",
)

app = BUNDLE(
    coll,
    name="Imprint.app",
    icon="assets/icon.icns",
    bundle_identifier="com.netrunner3000.imprint",
    info_plist={
        "CFBundleName": "Imprint",
        "CFBundleDisplayName": "Imprint",
        "CFBundleShortVersionString": "1.0.1",
        "CFBundleVersion": "1.0.1",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,   # allow dark mode
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        # App writes only to ~/Library/Application Support, but it reads the
        # user's ebook folder etc. — declare a usage string for Documents access.
        "NSDesktopFolderUsageDescription": "Imprint reads ebooks and saves outputs you choose.",
        "NSDocumentsFolderUsageDescription": "Imprint reads ebooks and saves outputs you choose.",
    },
)
