#!/usr/bin/env bash
# Build the PyInstaller directory bundle holding the assistant and its MCP runtime.
#
# Reproducible inputs: the locked dependency set plus this repository's own sources.
# Nothing is downloaded from `main` and no user configuration is read.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BUILD_DIR="${BUILD_DIR:-$ROOT/build}"
DIST_DIR="${DIST_DIR:-$ROOT/dist/desktop}"

rm -rf "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

"${PYINSTALLER:-pyinstaller}" \
  --clean --noconfirm --log-level WARN \
  --workpath "$BUILD_DIR/pyinstaller" \
  --distpath "$DIST_DIR" \
  packaging/proton-safe-assistant.spec

BUNDLE="$DIST_DIR/proton-safe-assistant"
test -x "$BUNDLE/proton-safe-assistant" || { echo "assistant executable missing" >&2; exit 1; }
test -x "$BUNDLE/proton-safe-mcp" || { echo "runtime executable missing" >&2; exit 1; }

# A bundle that starts on the build machine proves nothing about what it embedded.
# These checks run the bundled executables and read what they report, because pure
# Python modules live inside the archive and cannot be found on disk.
VERIFY_DIR="$(mktemp -d)"
trap 'rm -rf "$VERIFY_DIR"' EXIT
mkdir -p "$VERIFY_DIR/config/proton-safe-mcp"
chmod 700 "$VERIFY_DIR/config/proton-safe-mcp"
cat > "$VERIFY_DIR/config/proton-safe-mcp/config.toml" <<'TOML'
schema_version = 1

[bridge]
user = "verification@example.com"
imap_port = 1143
aliases = []
TOML
chmod 600 "$VERIFY_DIR/config/proton-safe-mcp/config.toml"

echo "Verifying the bundled runtime starts and reports a diagnosis..."
REPORT="$(XDG_STATE_HOME="$VERIFY_DIR/state" \
  "$BUNDLE/proton-safe-mcp" doctor --config "$VERIFY_DIR/config/proton-safe-mcp/config.toml" \
  || true)"
echo "$REPORT" | grep -q "Proton Safe MCP doctor" \
  || { echo "the bundled runtime did not produce a diagnosis" >&2; exit 1; }

echo "Verifying the keyring backend is embedded, not merely unreachable here..."
if echo "$REPORT" | grep -q "missing from this installation"; then
    echo "the Secret Service keyring backend was not bundled" >&2
    exit 1
fi

echo "Verifying the embedded plugin resources and the MCP tool surface..."
XDG_STATE_HOME="$VERIFY_DIR/state" XDG_DATA_HOME="$VERIFY_DIR/data" \
  "$BUNDLE/proton-safe-assistant" --verify-bundle \
  --config "$VERIFY_DIR/config/proton-safe-mcp/config.toml" \
  || { echo "bundle self-verification failed" >&2; exit 1; }

echo "Bundle built at $BUNDLE"
