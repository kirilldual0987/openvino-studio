#!/bin/sh
# OpenVINO Studio — Linux launcher. Copyright (c) 2026 ByKirilldual0987.
set -u
BASE="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$BASE" || exit 1
mkdir -p "$BASE/runtime/logs"

find_python() {
  for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    path="$(command -v "$candidate" 2>/dev/null || true)"
    if [ -n "$path" ] && "$path" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
      printf '%s' "$path"
      return 0
    fi
  done
  return 1
}

PY="$(find_python || true)"
if [ -z "$PY" ]; then
  if command -v zenity >/dev/null 2>&1; then
    zenity --error --title="OpenVINO Studio" --text="Не найден Python 3.10+. Установите python3 и python3-venv."
  elif command -v kdialog >/dev/null 2>&1; then
    kdialog --title "OpenVINO Studio" --error "Не найден Python 3.10+. Установите python3 и python3-venv."
  fi
  exit 1
fi

nohup "$PY" "$BASE/app/bootstrap.pyw" >> "$BASE/runtime/logs/linux-launcher.log" 2>&1 &
exit 0
