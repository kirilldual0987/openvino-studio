"""Environment and device information."""
from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config
from .util import human_size, log

_cache_lock = threading.Lock()
_cache: dict = {"time": 0.0, "probe": None}
_cache_ttl = 30

COMPONENTS = [
    {
        "id": "runtime",
        "name": "OpenVINO Runtime",
        "description": "Ядро инференса, устройства CPU/GPU/NPU, бенчмарк и изображения.",
        "packages": ["openvino", "pillow", "numpy"],
        "size_hint": "~250 МБ",
        "required": True,
    },
    {
        "id": "genai",
        "name": "OpenVINO GenAI",
        "description": "Чат с LLM, потоковая генерация и токенизаторы.",
        "packages": ["openvino-genai"],
        "size_hint": "~120 МБ",
        "required": False,
    },
    {
        "id": "convert",
        "name": "Конвертация и квантование",
        "description": "Optimum Intel, NNCF и PyTorch для экспорта моделей HF в OpenVINO IR.",
        "packages": ["optimum-intel[openvino]", "nncf", "torch", "transformers", "sentencepiece"],
        "size_hint": "~2–3 ГБ",
        "required": False,
    },
]

PACKAGE_DISTS = {
    "openvino": "openvino",
    "openvino_genai": "openvino-genai",
    "openvino-genai": "openvino-genai",
    "optimum": "optimum",
    "optimum-intel": "optimum-intel",
    "nncf": "nncf",
    "torch": "torch",
    "transformers": "transformers",
    "pillow": "pillow",
    "numpy": "numpy",
}


def _version(dist: str) -> str:
    try:
        return importlib.metadata.version(dist)
    except Exception:
        return ""


def components_status() -> list[dict]:
    versions = {name: _version(name) for name in set(PACKAGE_DISTS.values())}
    result = []
    for component in COMPONENTS:
        installed = all(versions.get(pkg.split("[")[0], "") for pkg in component["packages"])
        result.append(
            {
                "id": component["id"],
                "name": component["name"],
                "description": component["description"],
                "size_hint": component["size_hint"],
                "required": component["required"],
                "packages": component["packages"],
                "installed": installed,
                "versions": {
                    pkg.split("[")[0]: versions.get(pkg.split("[")[0], "") for pkg in component["packages"]
                },
            }
        )
    return result


def run_probe(timeout: int = 60) -> dict:
    worker = config.APP_DIR / "workers" / "system_probe.py"
    args_file = config.JOBS_DIR / "probe.json"
    config.ensure_dirs()
    args_file.write_text("{}", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["OVS_BASE"] = str(config.BASE_DIR)
    env["OVS_RUNTIME"] = str(config.RUNTIME_DIR)
    kwargs = {}
    if config.IS_WINDOWS:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        proc = subprocess.run(
            [config.python_executable(), str(worker), str(args_file)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            cwd=str(config.BASE_DIR),
            **kwargs,
        )
        for line in (proc.stdout or "").splitlines():
            if line.startswith("@@"):
                continue
            if line.strip().startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {
            "installed": False,
            "error": (proc.stderr or "").strip()[-800:] or "Не удалось получить сведения об OpenVINO.",
        }
    except subprocess.TimeoutExpired:
        return {"installed": False, "error": "Проверка устройств заняла слишком много времени."}
    except Exception as exc:
        return {"installed": False, "error": str(exc)}


def probe(force: bool = False) -> dict:
    with _cache_lock:
        if not force and _cache["probe"] is not None and time.time() - _cache["time"] < _cache_ttl:
            return _cache["probe"]
    result = run_probe()
    with _cache_lock:
        _cache["probe"] = result
        _cache["time"] = time.time()
    return result


def system_info(force_probe: bool = False) -> dict:
    try:
        usage = shutil.disk_usage(config.BASE_DIR)
        disk = {
            "total": usage.total,
            "free": usage.free,
            "used": usage.used,
            "total_label": human_size(usage.total),
            "free_label": human_size(usage.free),
            "used_label": human_size(usage.used),
            "percent": round(usage.used / usage.total * 100, 1) if usage.total else 0,
        }
    except Exception:
        disk = {"total": 0, "free": 0, "used": 0, "total_label": "—", "free_label": "—", "used_label": "—", "percent": 0}
    probe_data = probe(force=force_probe)
    settings = config.load_settings()
    return {
        "app_version": config.APP_VERSION,
        "python": sys.version.split()[0],
        "python_exe": sys.executable,
        "platform": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "base_path": str(config.BASE_DIR),
        "models_path": str(config.models_dir(settings)),
        "runtime_path": str(config.RUNTIME_DIR),
        "disk": disk,
        "components": components_status(),
        "openvino": probe_data,
        "settings": settings,
        "jobs_active": 0,
    }


def invalidate_probe() -> None:
    with _cache_lock:
        _cache["time"] = 0.0
