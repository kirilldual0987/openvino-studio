"""Small shared helpers."""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path

from . import config

_log_lock = threading.Lock()
_logger = None


def setup_logging(debug: bool = False) -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    config.ensure_dirs()
    logger = logging.getLogger("ovstudio")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    try:
        from logging.handlers import RotatingFileHandler

        handler = RotatingFileHandler(
            config.LOGS_DIR / "studio.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    except Exception:
        pass
    if sys.stderr is not None and debug:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(fmt)
        logger.addHandler(stream)
    _logger = logger
    return logger


def log(message: str, level: int = logging.INFO) -> None:
    logger = setup_logging()
    with _log_lock:
        logger.log(level, message)


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def human_size(num: float | int | None) -> str:
    if not num:
        return "0 Б"
    num = float(num)
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
    idx = 0
    while num >= 1024 and idx < len(units) - 1:
        num /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(num)} {units[idx]}"
    return f"{num:.2f} {units[idx]}".replace(".00", "")


def human_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0 or seconds > 86400 * 7:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} с"
    if seconds < 3600:
        return f"{seconds // 60} мин {seconds % 60:02d} с"
    return f"{seconds // 3600} ч {(seconds % 3600) // 60:02d} мин"


def atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def safe_name(name: str, fallback: str = "model") -> str:
    name = (name or "").strip().replace("/", "__").replace("\\", "__")
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", "_", name)
    name = name.strip(" ._")
    if not name:
        name = fallback
    if name.upper().split(".")[0] in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        name = "_" + name
    return name[:120]


def dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat().st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += dir_size(Path(entry.path))
            except OSError:
                continue
    except OSError:
        pass
    return total


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def parse_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def parse_float(value, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return max(minimum, min(maximum, number))


def local_http_url(port: int, path: str = "/") -> str:
    return f"http://127.0.0.1:{port}{path}"


def timestamp_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")
