#!/bin/bash
# Builds a double-clickable "Marker Cutter.app" that starts the local server and opens the page.
# The app points at THIS checkout, so don't move the folder afterwards (re-run this script if you do).
#
#   ./macos/build_launcher.sh            # creates ./Marker Cutter.app
#   ./macos/build_launcher.sh ~/Applications
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$HERE/../marker_cutter" && pwd)"
PYTHON="$(command -v python3 || true)"
OUT_DIR="${1:-$HERE/..}"

[ -n "$PYTHON" ] || { echo "python3 not found. Install Python 3 first." >&2; exit 1; }
case "$APP_DIR$PYTHON" in *\"*|*\\*) echo "Paths with quotes or backslashes aren't supported." >&2; exit 1;; esac

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
sed -e "s|__APP_DIR__|$APP_DIR|" -e "s|__PYTHON__|$PYTHON|" "$HERE/launcher.applescript.template" > "$TMP/launcher.applescript"

APP="$OUT_DIR/Marker Cutter.app"
rm -rf "$APP"
osacompile -o "$APP" "$TMP/launcher.applescript"
echo "Built: $APP"
echo "  server : $APP_DIR/server.py"
echo "  python : $PYTHON"
