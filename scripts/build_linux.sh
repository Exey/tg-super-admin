#!/bin/bash
# Build TG Admin Tools for Linux: one-file binary + one-dir bundle.
set -e
cd "$(dirname "$0")/.."

NAME="TgAdminTools"

if ! command -v python3 &> /dev/null; then
    echo "❌ python3 not found. Install Python 3.10+ first."; exit 1
fi

python3 -m venv .venv-build 2>/dev/null || true
source .venv-build/bin/activate
pip install -U pip
pip install -r requirements.txt pyinstaller

# Variant 1: single executable file
pyinstaller --noconfirm --clean --onefile \
    --name "$NAME" --distpath dist/onefile main.py

# Variant 2: one-dir bundle (starts faster)
pyinstaller --noconfirm --clean \
    --name "$NAME" --distpath dist/onedir main.py

echo ""
echo "✅ Done:"
echo "   dist/onefile/$NAME              (single file)"
echo "   dist/onedir/$NAME/$NAME         (folder bundle)"
echo ""
echo "If Qt complains about xcb, install: libxcb-cursor0 (Debian/Ubuntu)"
