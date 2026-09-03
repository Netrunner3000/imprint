# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Create & Publish — self-contained macOS .app bundle.

Build:   .venv/bin/pyinstaller --noconfirm CreateAndPublish.spec
Output:  dist/Create & Publish.app
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = [
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    "services.narrator.converter",   # invoked via the --narrator-worker sentinel
]

# SDKs / libs with data files or plugin discovery that static analysis can miss.
for pkg in ("google.genai", "tiktoken", "anthropic", "openai", "certifi"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Read-only resources seeded into the writable user-data dir on first launch.
datas += [
    ("config", "config"),
    ("README.md", "."),
    (".env.example", "."),
    ("docs/agents", "docs/agents"),   # per-agent capability sheets (Docs button)
]

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
        "agents.course_agent",
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
    name="Create & Publish",
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
    name="Create & Publish",
)

app = BUNDLE(
    coll,
    name="Create & Publish.app",
    icon="assets/icon.icns",
    bundle_identifier="com.netrunner3000.createandpublish",
    info_plist={
        "CFBundleName": "Create & Publish",
        "CFBundleDisplayName": "Create & Publish",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,   # allow dark mode
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        # App writes only to ~/Library/Application Support, but it reads the
        # user's ebook folder etc. — declare a usage string for Documents access.
        "NSDesktopFolderUsageDescription": "Create & Publish reads ebooks and saves outputs you choose.",
        "NSDocumentsFolderUsageDescription": "Create & Publish reads ebooks and saves outputs you choose.",
    },
)
