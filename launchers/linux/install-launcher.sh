#!/bin/sh
# Adds OpenVINO Studio to the application menu. Copyright (c) 2026 ByKirilldual0987.
set -u
BASE="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
TARGET="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$TARGET"
cat > "$TARGET/openvino-studio.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=OpenVINO Studio
Comment=Локальный AI на Intel OpenVINO
Exec="$BASE/launchers/linux/start-openvino-studio.sh"
Path=$BASE
Icon=$BASE/app/assets/logo-128.png
Terminal=false
Categories=Development;Science;Education;
StartupNotify=false
EOF
chmod +x "$TARGET/openvino-studio.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$TARGET" >/dev/null 2>&1 || true
fi
printf 'Ярлык создан: %s\n' "$TARGET/openvino-studio.desktop"
