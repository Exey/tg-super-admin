#!/bin/bash
# Build TG Admin Tools for macOS: one-file binary + .app bundle.
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
pyinstaller --noconfirm --clean --windowed --onefile \
    --name "$NAME" --distpath dist/onefile main.py

# Variant 2: .app bundle (starts faster, easier to codesign)
pyinstaller --noconfirm --clean --windowed \
    --name "$NAME" --distpath dist/app main.py

echo ""
echo "✅ Done:"
echo "   dist/onefile/$NAME        (single file)"
echo "   dist/app/$NAME.app        (app bundle)"
echo ""
echo "Note: unsigned apps need right-click → Open the first time,"
echo "or: xattr -dr com.apple.quarantine dist/app/$NAME.app"
