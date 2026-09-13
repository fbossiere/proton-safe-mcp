#!/usr/bin/env bash
# Assemble the Ubuntu package from an already-built bundle.
#
# The package installs system files only. It never looks for a user session, creates a
# configuration or touches a keyring with system privileges, and removing it leaves the
# user's private data in place.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DIST_DIR="${DIST_DIR:-$ROOT/dist/desktop}"
BUNDLE="$DIST_DIR/proton-safe-assistant"
STAGE="${STAGE:-$ROOT/build/deb}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/proton_safe_mcp/__init__.py)"
ARCH="${ARCH:-amd64}"
PACKAGE="proton-safe-assistant_${VERSION}_${ARCH}.deb"

test -d "$BUNDLE" || { echo "run packaging/build_bundle.sh first" >&2; exit 1; }

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" \
         "$STAGE/opt/proton-safe-assistant" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/pixmaps" \
         "$STAGE/usr/share/doc/proton-safe-assistant"

cp -a "$BUNDLE/." "$STAGE/opt/proton-safe-assistant/"
install -m 0644 packaging/proton-safe-assistant.desktop \
  "$STAGE/usr/share/applications/proton-safe-assistant.desktop"
install -m 0644 LICENSE "$STAGE/usr/share/doc/proton-safe-assistant/copyright"
# The available artwork is a banner, not a square app icon, so it goes to the
# size-agnostic pixmaps fallback rather than claiming a hicolor size it does not have.
install -m 0644 docs/assets/proton-mcp-safe.png \
  "$STAGE/usr/share/pixmaps/proton-safe-assistant.png"

# Only the graphical entry point is exposed on PATH. The runtime deliberately stays in
# /opt so it cannot shadow an existing `proton-safe-mcp` in ~/.local/bin.
ln -s /opt/proton-safe-assistant/proton-safe-assistant "$STAGE/usr/bin/proton-safe-assistant"

cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: proton-safe-assistant
Version: ${VERSION}
Section: net
Priority: optional
Architecture: ${ARCH}
Depends: libc6, libglib2.0-0t64 | libglib2.0-0, libdbus-1-3, libfontconfig1, libfreetype6, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-keysyms1, libxcb-shape0, libxcb-randr0, libxcb-render-util0, libxcb-xinerama0, libegl1, libgl1
Recommends: gnome-keyring
Maintainer: Francois Bossiere <noreply@users.noreply.github.com>
Homepage: https://fbossiere.github.io/proton-safe-mcp/
Description: Connect Proton Mail to a local AI assistant, read and draft only
 Proton Safe sets up a local Proton Mail connection for ChatGPT desktop or Codex
 running on the same computer. The assistant can search, read and prepare drafts;
 it cannot send, delete or move messages.
 .
 It needs Proton Mail Bridge, which is installed separately from proton.me.
 The Bridge credential is kept in the session keyring and never in a file.
CONTROL

cat > "$STAGE/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
# System-wide desktop database only. No user session is searched and no per-user
# configuration or keyring entry is created here.
if [ "$1" = "configure" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
fi
POSTINST

cat > "$STAGE/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
# Private user data under ~/.config, ~/.local and the keyring is deliberately left
# alone: removing the package must not delete someone's settings or credential.
if [ "$1" = "remove" ] && command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
POSTRM

chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"
find "$STAGE/opt" -type d -exec chmod 0755 {} +

mkdir -p "$DIST_DIR"
dpkg-deb --root-owner-group --build "$STAGE" "$DIST_DIR/$PACKAGE"
echo "Package built at $DIST_DIR/$PACKAGE"
echo "Installed size: $(du -sh "$STAGE" | cut -f1)"

# Provenance, so a tester can tie the downloaded artefact to the exact sources that
# produced it. The package itself is never committed to the repository.
SOURCE_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
if ! git -C "$ROOT" diff --quiet HEAD 2>/dev/null; then
    SOURCE_COMMIT="$SOURCE_COMMIT (working tree modified)"
fi
# On a pull request, CI checks out the merge commit, which is not a commit on the branch.
# Recording the run and the branch gives a tester something they can actually navigate to.
CI_CONTEXT=""
if [ -n "${GITHUB_RUN_ID:-}" ]; then
    CI_CONTEXT="ci run:        ${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID}
branch:        ${GITHUB_HEAD_REF:-${GITHUB_REF_NAME:-unknown}}
note:          on a pull request the commit above is CI's merge commit, not a branch commit
"
fi
BUILD_HOST="$( (. /etc/os-release 2>/dev/null && printf '%s' "$PRETTY_NAME") || printf unknown ) $(uname -m)"
DIGEST="$(cd "$DIST_DIR" && sha256sum "$PACKAGE")"
printf '%s\n' "$DIGEST" > "$DIST_DIR/$PACKAGE.sha256"

cat > "$DIST_DIR/BUILD-PROVENANCE.txt" <<PROVENANCE
Proton Safe desktop assistant — build provenance

package:        $PACKAGE
sha256:         ${DIGEST%% *}
engine version: $VERSION
source commit:  $SOURCE_COMMIT
built on:       $BUILD_HOST
$CI_CONTEXT

Verify before installing:

    sha256sum -c $PACKAGE.sha256

This package is produced from the sources at the commit above. It is never committed to
the repository; obtain it from the CI build artefacts or build it yourself with
packaging/build_bundle.sh followed by packaging/build_deb.sh.
PROVENANCE

echo "Digest: ${DIGEST%% *}"
echo "Source commit: $SOURCE_COMMIT"

# Prove the package really carries both executables and the launcher, from the archive
# itself rather than from the staging directory.
CONTENTS="$(dpkg-deb --contents "$DIST_DIR/$PACKAGE")"
for expected in \
    "./opt/proton-safe-assistant/proton-safe-assistant" \
    "./opt/proton-safe-assistant/proton-safe-mcp" \
    "./usr/bin/proton-safe-assistant" \
    "./usr/share/applications/proton-safe-assistant.desktop"; do
    printf '%s\n' "$CONTENTS" | grep -q -- "$expected" \
      || { echo "missing from the package: $expected" >&2; exit 1; }
done
# A historic ~/.local/bin/proton-safe-mcp must keep working: the package exposes only
# its graphical entry point on PATH.
printf '%s\n' "$CONTENTS" | grep -q "./usr/bin/proton-safe-mcp$" \
  && { echo "the package must not place proton-safe-mcp on PATH" >&2; exit 1; }
echo "Package contents verified."
