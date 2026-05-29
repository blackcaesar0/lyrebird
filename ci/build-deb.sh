#!/bin/sh
# Build a Debian/Ubuntu (.deb) package for Lyrebird.
#
# Produces ci/lyrebird_<version>_all.deb installable with:
#     sudo apt install ./lyrebird_<version>_all.deb
#
# Requires: dpkg-deb (from dpkg). No root/fakeroot needed.
set -eu

VERSION="1.4.0"
ARCH="all"
PKG="lyrebird_${VERSION}_${ARCH}"

# Resolve paths relative to the repository root (this script lives in ci/).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/$PKG"

echo "[build-deb] Cleaning previous build"
rm -rf "$BUILD_DIR"

BIN_PATH="/usr/bin"
SHARE_PATH="/usr/share/lyrebird"
DESKTOP_PATH="/usr/share/applications"

echo "[build-deb] Staging files"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR$BIN_PATH"
mkdir -p "$BUILD_DIR$SHARE_PATH"
mkdir -p "$BUILD_DIR$DESKTOP_PATH"
mkdir -p "$BUILD_DIR/usr/share/doc/lyrebird"

# Application source
cp -r "$ROOT_DIR/app" "$BUILD_DIR$SHARE_PATH/"
cp "$ROOT_DIR/app.py" "$BUILD_DIR$SHARE_PATH/"
cp "$ROOT_DIR/icon.png" "$BUILD_DIR$SHARE_PATH/"

# Strip caches that may have been created during development
find "$BUILD_DIR$SHARE_PATH" -name '__pycache__' -type d -prune -exec rm -rf {} +

# Launcher
cp "$ROOT_DIR/lyrebird" "$BUILD_DIR$BIN_PATH/lyrebird"
chmod 755 "$BUILD_DIR$BIN_PATH/lyrebird"

# Desktop entry (substitute the install paths)
sed -e "s|\${BIN_PATH}|$BIN_PATH|g" \
    -e "s|\${SHARE_PATH}|$SHARE_PATH|g" \
    "$ROOT_DIR/lyrebird.desktop" > "$BUILD_DIR$DESKTOP_PATH/lyrebird.desktop"
chmod 644 "$BUILD_DIR$DESKTOP_PATH/lyrebird.desktop"

# Docs
cp "$ROOT_DIR/README.md" "$ROOT_DIR/CHANGELOG.md" "$ROOT_DIR/LICENSE" \
    "$BUILD_DIR/usr/share/doc/lyrebird/"

# Control metadata
cat > "$BUILD_DIR/DEBIAN/control" <<EOF
Package: lyrebird
Version: $VERSION
Section: sound
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.7), python3-gi, gir1.2-gtk-3.0, python3-toml, sox, libsox-fmt-pulse, pavucontrol, pulseaudio-utils, pipewire-pulse | pulseaudio
Maintainer: Lyrebird maintainers
Homepage: https://github.com/lyrebird-voice-changer/lyrebird
Description: Simple and powerful voice changer for Linux
 Lyrebird is a voice changer for Linux written with Python and GTK.
 .
  * Built in effects for accurate male and female voices.
  * Create, edit and delete custom presets in the GUI.
  * Manual pitch scale for finer adjustment.
  * Monitor mode to hear your own effected voice.
  * Creates its own temporary virtual input device.
EOF

# Normalise permissions
find "$BUILD_DIR$SHARE_PATH" -type d -exec chmod 755 {} +
find "$BUILD_DIR$SHARE_PATH" -type f -exec chmod 644 {} +
chmod 755 "$BUILD_DIR$SHARE_PATH/app.py"

echo "[build-deb] Building package"
dpkg-deb --root-owner-group --build "$BUILD_DIR" "$SCRIPT_DIR/$PKG.deb"

echo "[build-deb] Done: ci/$PKG.deb"
