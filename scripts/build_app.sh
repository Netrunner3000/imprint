#!/usr/bin/env bash
# Build & install "Sentinel AI.app" — a self-contained macOS application bundle
# produced by PyInstaller (bundles its own Python + every dependency). Unlike a
# dev checkout, the app does NOT need the project's .venv or even the project
# folder once installed.
#
#   ./scripts/build_app.sh            # build + install to /Applications
#   ./scripts/build_app.sh --no-install   # build only (dist/Sentinel AI.app)
#
# IMPORTANT: the bundle freezes the CODE at build time. After editing main.py (or
# anything else), re-run this script to refresh the installed app.
#
# Writable state (SQLite DB, saved chats, logs, editable config, API keys) lives
# in  ~/Library/Application Support/Sentinel AI/  — seeded on first launch and
# preserved across rebuilds. Put API keys in that folder's .env file.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="Sentinel AI"
APP_BUNDLE="${APP_NAME}.app"
DIST_APP="${PROJECT_ROOT}/dist/${APP_BUNDLE}"
INSTALLED="/Applications/${APP_BUNDLE}"
PY="${PROJECT_ROOT}/.venv/bin/python"

cd "$PROJECT_ROOT"

echo "▸ Building ${APP_BUNDLE} with PyInstaller (this takes ~1 min)…"
"$PY" -m PyInstaller --noconfirm --clean SentinelAI.spec

if [ "${1:-}" = "--no-install" ]; then
    echo "✓ Built: ${DIST_APP}"
    exit 0
fi

echo "▸ Installing to ${INSTALLED}…"
# Stop any running instance so Launch Services picks up the new binary.
pkill -f "${APP_BUNDLE}/Contents/MacOS" 2>/dev/null || true
sleep 1
rm -rf "$INSTALLED"
cp -R "$DIST_APP" "$INSTALLED"

# Clear any extended attributes and ad-hoc sign so Gatekeeper allows the local app.
xattr -cr "$INSTALLED" 2>/dev/null || true
codesign --force --deep --sign - "$INSTALLED"

# Register with Launch Services so it shows up in Spotlight / Launchpad.
LSREG="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
"$LSREG" -f "$INSTALLED"

echo ""
echo "✓ Installed: ${INSTALLED}"
echo "  Launch it from Spotlight, Launchpad, or /Applications."
echo "  API keys: ~/Library/Application Support/${APP_NAME}/.env"
