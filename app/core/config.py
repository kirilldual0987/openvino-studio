"""Application paths, constants and persistent settings."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "OpenVINO Studio"
APP_VERSION = "1.1.0"
APP_TAGLINE = "Локальный AI на Intel"

BASE_DIR = Path(__file__).resolve().parents[2]
APP_DIR = BASE_DIR / "app"
WEB_DIR = APP_DIR / "web"
RUNTIME_DIR = BASE_DIR / "runtime"
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = RUNTIME_DIR / "logs"
JOBS_DIR = RUNTIME_DIR / "jobs"
TMP_DIR = RUNTIME_DIR / "tmp"
CACHE_DIR = RUNTIME_DIR / "cache"
HF_HOME = RUNTIME_DIR / "hf"

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"

DEFAULT_SETTINGS = {
    "theme": "system",
    "hf_token": "",
    "proxy": "",
    "default_device": "CPU",
    "num_threads": 0,
    "models_dir": "models",
    "open_mode": "app",
    "confirm_delete": True,
    "last_seen_version": APP_VERSION,
}

_lock_import = None


def ensure_dirs() -> None:
    for directory in (RUNTIME_DIR, MODELS_DIR, LOGS_DIR, JOBS_DIR, TMP_DIR, CACHE_DIR, HF_HOME):
        directory.mkdir(parents=True, exist_ok=True)


def settings_path() -> Path:
    return RUNTIME_DIR / "settings.json"


def load_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    path = settings_path()
    try:
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key, value in loaded.items():
                    if key in DEFAULT_SETTINGS:
                        data[key] = value
    except Exception:
        pass
    # Never silently relocate the model library.
    if not data.get("models_dir"):
        data["models_dir"] = str(MODELS_DIR)
    return data


def save_settings(data: dict) -> dict:
    current = load_settings()
    for key in DEFAULT_SETTINGS:
        if key in data:
            current[key] = data[key]
    current["models_dir"] = current.get("models_dir") or str(MODELS_DIR)
    ensure_dirs()
    tmp = settings_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, settings_path())
    return current


def models_dir(settings: dict | None = None) -> Path:
    settings = settings or load_settings()
    raw = settings.get("models_dir") or str(MODELS_DIR)
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def python_executable() -> str:
    """Use python.exe for workers on Windows so stdout pipes are reliable."""
    exe = Path(sys.executable)
    if IS_WINDOWS and exe.name.lower() == "pythonw.exe":
        candidate = exe.with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return sys.executable


def apply_env() -> None:
    """Environment for every worker: keep caches, temp and telemetry on the external drive."""
    ensure_dirs()
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ["HF_HOME"] = str(HF_HOME)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["OV_CACHE_DIR"] = str(CACHE_DIR)
    os.environ["TMP"] = str(TMP_DIR)
    os.environ["TEMP"] = str(TMP_DIR)
    os.environ["TMPDIR"] = str(TMP_DIR)
    os.environ["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    os.environ["PIP_NO_INPUT"] = "1"
    os.environ["PIP_CACHE_DIR"] = str(RUNTIME_DIR / "pip-cache")
