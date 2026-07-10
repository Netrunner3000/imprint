# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Sentinel AI — self-contained macOS .app bundle.

Build:   .venv/bin/pyinstaller --noconfirm SentinelAI.spec
Output:  dist/Sentinel AI.app
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = [
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    "services.narrator.converter",   # invoked via the --narrator-worker sentinel
    "whois",                         # lazy import in providers/domain_lookup
    "dns", "dns.resolver",           # lazy import in providers/domain_lookup
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
    name="Sentinel AI",
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
    name="Sentinel AI",
)

app = BUNDLE(
    coll,
    name="Sentinel AI.app",
    icon="assets/icon.icns",
    bundle_identifier="com.netrunner3000.sentinelai",
    info_plist={
        "CFBundleName": "Sentinel AI",
        "CFBundleDisplayName": "Sentinel AI",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,   # allow dark mode
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.developer-tools",
        # App writes only to ~/Library/Application Support, but it reads the
        # user's ebook folder etc. — declare a usage string for Documents access.
        "NSDesktopFolderUsageDescription": "Sentinel AI reads ebooks and saves outputs you choose.",
        "NSDocumentsFolderUsageDescription": "Sentinel AI reads ebooks and saves outputs you choose.",
    },
)
