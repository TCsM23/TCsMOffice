#!/usr/bin/env bash
# Wrap PyInstaller's dist/TCsOffice/ into dist/TCsOffice-<version>-x86_64.AppImage.
#   packaging/linux/build_appimage.sh 1.0.17
set -euo pipefail
VERSION="$1"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APPDIR="$ROOT/build/TCsOffice.AppDir"
rm -rf "$APPDIR" && mkdir -p "$APPDIR/usr/bin"
cp -r "$ROOT/dist/TCsOffice/." "$APPDIR/usr/bin/"
cp "$ROOT/packaging/linux/tcsoffice.desktop" "$APPDIR/"
cp "$ROOT/office/assets/icon-512.png" "$APPDIR/tcsoffice.png"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/TCsOffice" "$@"
RUN
chmod +x "$APPDIR/AppRun"
TOOL="$ROOT/build/appimagetool"
if [ ! -x "$TOOL" ]; then
  curl -sSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "$ROOT/dist/TCsOffice-$VERSION-x86_64.AppImage"
