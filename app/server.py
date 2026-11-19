"""OpenVINO Studio local server.

A dependency-free HTTP server that powers the desktop UI, runs worker
processes and keeps everything on the external drive.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core import config, hf, models, system
from core.jobs import JobManager, _hidden_kwargs
from core.util import (
    human_size,
    is_relative_to,
    log,
    parse_float,
    parse_int,
    safe_name,
    setup_logging,
)
from core import util

MAX_BODY = 32 * 1024 * 1024
SERVER_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


CURATED = [
    {
        "repo": "OpenVINO/TinyLlama-1.1B-Chat-v1.0-int4-ov",
        "title": "TinyLlama 1.1B Chat",
        "desc": "Лёгкий старт: быстрый чат на CPU, всего 0.6 ГБ.",
        "size": 640_000_000,
        "kind": "LLM",
        "badges": ["INT4", "0.6 ГБ", "чат"],
        "tone": "violet",
    },
    {
        "repo": "OpenVINO/Qwen2.5-1.5B-Instruct-int4-ov",
        "title": "Qwen2.5 1.5B Instruct",
        "desc": "Компактная модель с хорошим русским и инструкциями.",
        "size": 940_000_000,
        "kind": "LLM",
        "badges": ["INT4", "1.0 ГБ", "RU"],
        "tone": "blue",
    },
    {
        "repo": "OpenVINO/Qwen3-4B-int4-ov",
        "title": "Qwen3 4B",
        "desc": "Сильный баланс качества и скорости для повседневных задач.",
        "size": 2_290_000_000,
        "kind": "LLM",
        "badges": ["INT4", "2.3 ГБ", "чат"],
        "tone": "green",
    },
    {
        "repo": "OpenVINO/Phi-4-mini-instruct-int4-ov",
        "title": "Phi-4 mini Instruct",
        "desc": "Рассуждения и код в компактном формате от Microsoft.",
        "size": 2_390_000_000,
        "kind": "LLM",
        "badges": ["INT4", "2.4 ГБ", "reasoning"],
        "tone": "orange",
    },
    {
        "repo": "OpenVINO/Qwen3-8B-int4-ov",
        "title": "Qwen3 8B",
        "desc": "Максимальное качество среди компактных Qwen3 для GPU.",
        "size": 4_880_000_000,
        "kind": "LLM",
        "badges": ["INT4", "4.9 ГБ", "GPU"],
        "tone": "pink",
    },
    {
        "repo": "OpenVINO/Qwen2.5-Coder-7B-Instruct-int8-ov",
        "title": "Qwen2.5 Coder 7B",
        "desc": "Помощник по коду: генерация, объяснение и рефакторинг.",
        "size": 7_650_000_000,
        "kind": "LLM",
        "badges": ["INT8", "7.7 ГБ", "код"],
        "tone": "teal",
    },
    {
        "repo": "OpenVINO/gemma-4-E2B-it-int4-ov",
        "title": "Gemma 4 E2B",
        "desc": "Мультимодальная модель: понимает изображения и отвечает на вопросы о них.",
        "size": 4_360_000_000,
        "kind": "VLM",
        "badges": ["INT4", "4.4 ГБ", "VLM"],
        "tone": "pink",
    },
    {
        "repo": "OpenVINO/gemma-4-E4B-it-int4-ov",
        "title": "Gemma 4 E4B",
        "desc": "Более сильная Gemma 4 для детальных описаний и визуальных задач.",
        "size": 6_540_000_000,
        "kind": "VLM",
        "badges": ["INT4", "6.5 ГБ", "VLM"],
        "tone": "violet",
    },
    {
        "repo": "OpenVINO/YOLO11n-int8-ov",
        "title": "YOLO11n",
        "desc": "Детекция объектов в реальном времени на CPU.",
        "size": 3_400_000,
        "kind": "Детекция",
        "badges": ["INT8", "3.4 МБ", "vision"],
        "tone": "red",
    },
    {
        "repo": "OpenVINO/resnet50-int8-ov",
        "title": "ResNet-50",
        "desc": "Классификация изображений по 1000 категориям.",
        "size": 26_000_000,
        "kind": "Классификация",
        "badges": ["INT8", "26 МБ", "vision"],
        "tone": "blue",
    },

]


def find_model_dir(model_id: str) -> Path:
    root = config.models_dir().resolve()
    target = (root / model_id).resolve()
    if not is_relative_to(target, root) or target == root or not target.is_dir():
        raise ApiError("Модель не найдена в библиотеке.", 404)
    return target


def public_settings(settings: dict) -> dict:
    data = dict(settings)
    data["hf_token_set"] = bool(settings.get("hf_token"))
    data.pop("hf_token", None)
    return data


def open_folder(path: Path) -> None:
    if config.IS_WINDOWS:
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif config.IS_MAC:
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def open_app_window(url: str) -> None:
    """Open a chromeless app window when Edge/Chrome is available."""
    if config.IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        candidates = [
            Path(pf86) / "Microsoft/Edge/Application/msedge.exe",
            Path(pf) / "Microsoft/Edge/Application/msedge.exe",
            Path(local) / "Microsoft/Edge/Application/msedge.exe",
            Path(pf) / "Google/Chrome/Application/chrome.exe",
            Path(pf86) / "Google/Chrome/Application/chrome.exe",
            Path(local) / "Google/Chrome/Application/chrome.exe",
        ]
        for exe in candidates:
            if exe.exists():
                try:
                    subprocess.Popen(
                        [
                            str(exe),
                            f"--app={url}",
                            "--start-maximized",
                            "--no-first-run",
                            "--no-default-browser-check",
                            "--disable-features=Translate",
                        ],
                        close_fds=True,
                    )
                    return
                except Exception as exc:
                    log(f"browser start failed: {exc}")
    try:
        webbrowser.open(url)
    except Exception as exc:
        log(f"webbrowser failed: {exc}")


class StudioHandler(BaseHTTPRequestHandler):
    server_version = f"OpenVINOStudio/{config.APP_VERSION}"
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------------- helpers
    def log_message(self, fmt, *args):
        log("http: " + (fmt % args), 10)

    def log_error(self, fmt, *args):
        log("http error: " + (fmt % args), 30)

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        try:
            parsed = urllib.parse.urlparse(origin)
        except Exception:
            return False
        return parsed.hostname in ("127.0.0.1", "localhost") and parsed.port == self.server.server_port

    def _read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ApiError("Слишком большой запрос.", 413)
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ApiError("Некорректный JSON в запросе.", 400) from exc
        if not isinstance(data, dict):
            raise ApiError("Ожидался JSON-объект.", 400)
        return data

    def _send_json(self, data, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_error_json(self, message: str, status: int = 400) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _serve_static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"
        relative = urllib.parse.unquote(path.lstrip("/"))
        target = (config.WEB_DIR / relative).resolve()
        if not is_relative_to(target, config.WEB_DIR) or not target.is_file():
            self._send_error_json("Файл не найден.", 404)
            return
        mime, _ = mimetypes.guess_type(str(target))
        if target.suffix == ".woff2":
            mime = "font/woff2"
        if target.suffix == ".ttf":
            mime = "font/ttf"
        if target.suffix == ".js":
            mime = "text/javascript; charset=utf-8"
        if target.suffix == ".css":
            mime = "text/css; charset=utf-8"
        if target.suffix == ".svg":
            mime = "image/svg+xml"
        mime = mime or "application/octet-stream"
        try:
            data = target.read_bytes()
        except OSError:
            self._send_error_json("Не удалось прочитать файл.", 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ------------------------------------------------------------------- HTTP
    def do_GET(self):
        self.server.last_activity = time.time()  # type: ignore[attr-defined]
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            self._serve_static(path)
            return
        try:
            query = urllib.parse.parse_qs(parsed.query)
            getter = {
                "/api/ping": self.api_ping,
                "/api/system": self.api_system,
                "/api/settings": self.api_settings,
                "/api/models": self.api_models,
                "/api/jobs": self.api_jobs,
                "/api/hf/search": self.api_hf_search,
                "/api/hf/model": self.api_hf_model,
                "/api/hf/curated": self.api_curated,
                "/api/benchmarks": self.api_benchmarks,
                "/api/logs": self.api_logs,
                "/api/health": self.api_ping,
            }.get(path)
            if not getter:
                raise ApiError("Метод API не найден.", 404)
            getter(query)
        except ApiError as exc:
            self._send_error_json(str(exc), exc.status)
        except hf.HFError as exc:
            self._send_error_json(str(exc), 502 if exc.status != 400 else 400)
        except Exception as exc:
            log(f"GET {path} failed: {exc}\n{traceback.format_exc()}", 40)
            self._send_error_json("Внутренняя ошибка сервера. Подробности в журнале.", 500)

    def do_POST(self):
        self.server.last_activity = time.time()  # type: ignore[attr-defined]
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not self._origin_ok():
            self._send_error_json("Запрос отклонён: недопустимый Origin.", 403)
            return
        try:
            body = self._read_body()
            if path == "/api/chat":
                try:
                    self.api_chat(body)
                except Exception as exc:
                    log(f"chat endpoint failed: {exc}", 40)
                return
            if path == "/api/vlm":
                try:
                    self.api_vlm(body)
                except Exception as exc:
                    log(f"vlm endpoint failed: {exc}", 40)
                return
            handler = {
                "/api/settings": self.api_settings_save,
                "/api/models/delete": self.api_model_delete,
                "/api/models/reveal": self.api_model_reveal,
                "/api/models/download": self.api_download,
                "/api/jobs/cancel": self.api_job_cancel,
                "/api/benchmark": self.api_benchmark,
                "/api/image": self.api_image,
                "/api/convert": self.api_convert,
                "/api/install": self.api_install,
                "/api/open-folder": self.api_open_folder,
                "/api/system/refresh": self.api_system_refresh,
                "/api/shutdown": self.api_shutdown,
            }.get(path)
            if not handler:
                raise ApiError("Метод API не найден.", 404)
            handler(body)
        except ApiError as exc:
            self._send_error_json(str(exc), exc.status)
        except hf.HFError as exc:
            self._send_error_json(str(exc), 502)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            log(f"POST {path} failed: {exc}\n{traceback.format_exc()}", 40)
            try:
                self._send_error_json("Внутренняя ошибка сервера. Подробности в журнале.", 500)
            except Exception:
                pass

    # -------------------------------------------------------------------- API
    def api_ping(self, _query=None):
        self._send_json(
            {
                "ok": True,
                "app": config.APP_NAME,
                "version": config.APP_VERSION,
                "pid": os.getpid(),
                "jobs": self.server.jobs.active_count(),  # type: ignore[attr-defined]
            }
        )

    def api_system(self, query):
        force = bool(query.get("refresh")) or query.get("refresh", [""])[0] == "1"
        data = system.system_info(force_probe=force)
        data["jobs_active"] = self.server.jobs.active_count()  # type: ignore[attr-defined]
        data["settings"] = public_settings(data["settings"])
        self._send_json(data)

    def api_system_refresh(self, _body):
        system.invalidate_probe()
        data = system.system_info(force_probe=True)
        data["settings"] = public_settings(data["settings"])
        self._send_json(data)

    def api_settings(self, _query=None):
        self._send_json(public_settings(config.load_settings()))

    def api_settings_save(self, body):
        current = config.load_settings()
        patch = {}
        if "theme" in body and body["theme"] in ("system", "light", "dark"):
            patch["theme"] = body["theme"]
        if "default_device" in body:
            patch["default_device"] = str(body["default_device"])[:32]
        if "num_threads" in body:
            patch["num_threads"] = parse_int(body["num_threads"], 0, 0, 256)
        if "proxy" in body:
            patch["proxy"] = str(body["proxy"] or "").strip()[:500]
        if body.get("clear_hf_token"):
            patch["hf_token"] = ""
        elif body.get("hf_token"):
            patch["hf_token"] = str(body["hf_token"]).strip()[:500]
        if "confirm_delete" in body:
            patch["confirm_delete"] = bool(body["confirm_delete"])
        if "models_dir" in body and body["models_dir"]:
            path = Path(str(body["models_dir"])).expanduser()
            if not path.is_absolute():
                raise ApiError("Путь к моделям должен быть абсолютным.")
            path.mkdir(parents=True, exist_ok=True)
            patch["models_dir"] = str(path)
        settings = config.save_settings(patch)
        log(f"settings updated: {list(patch)}")
        self._send_json({"ok": True, "settings": public_settings(settings)})

    def api_models(self, _query=None):
        data = models.library_summary()
        self._send_json(data)

    def api_model_delete(self, body):
        model_id = str(body.get("id") or "")
        if not model_id:
            raise ApiError("Не указана модель.")
        models.delete_model(model_id)
        log(f"model deleted: {model_id}")
        self._send_json({"ok": True, "library": models.library_summary()})

    def api_model_reveal(self, body):
        model_id = str(body.get("id") or "")
        if model_id:
            path = find_model_dir(model_id)
        else:
            path = config.models_dir()
        open_folder(path)
        self._send_json({"ok": True, "path": str(path)})

    def api_jobs(self, _query=None):
        self._send_json(
            {
                "jobs": self.server.jobs.list(),  # type: ignore[attr-defined]
                "active": self.server.jobs.active_count(),  # type: ignore[attr-defined]
            }
        )

    def api_job_cancel(self, body):
        job_id = str(body.get("id") or "")
        ok = self.server.jobs.cancel(job_id)  # type: ignore[attr-defined]
        self._send_json({"ok": ok})

    def api_curated(self, _query=None):
        self._send_json({"models": CURATED})

    def api_hf_search(self, query):
        q = (query.get("q") or [""])[0].strip()
        task = (query.get("task") or [""])[0].strip()
        sort = (query.get("sort") or ["downloads"])[0]
        author = (query.get("author") or [""])[0].strip()
        limit = parse_int((query.get("limit") or ["30"])[0], 30, 1, 60)
        items = hf.search(query=q, task=task, author=author, sort=sort, limit=limit)
        self._send_json({"models": items, "count": len(items)})

    def api_hf_model(self, query):
        repo = (query.get("repo") or [""])[0]
        self._send_json(hf.model_detail(repo))

    def api_download(self, body):
        repo = str(body.get("repo") or "").strip().strip("/")
        if not repo or repo.count("/") != 1:
            raise ApiError("Укажите модель в формате organization/model.")
        settings = config.load_settings()
        dest = safe_name(repo)
        existing = config.models_dir() / dest
        if existing.exists() and (existing / ".ovstudio.json").exists():
            meta = models.read_meta(existing)
            if not meta.get("incomplete"):
                raise ApiError("Эта модель уже скачана в библиотеку.", 409)
        title = repo.split("/")[-1]
        job = self.server.jobs.start(  # type: ignore[attr-defined]
            "download.py",
            {
                "repo": repo,
                "dest": dest,
                "token": settings.get("hf_token") or "",
                "proxy": settings.get("proxy") or "",
                "revision": "main",
            },
            title=f"Загрузка {title}",
            kind="download",
        )
        log(f"download started: {repo} ({job.id})")
        self._send_json({"ok": True, "job": job.to_dict(with_logs=False)})

    def api_benchmark(self, body):
        model_id = str(body.get("model_id") or "")
        folder = find_model_dir(model_id)
        device = validate_device(str(body.get("device") or ""), config.load_settings())
        iterations = parse_int(body.get("iterations"), 10, 1, 100)
        warmup = parse_int(body.get("warmup"), 2, 0, 20)
        mode = str(body.get("mode") or "auto")
        if mode not in ("auto", "classic", "llm"):
            mode = "auto"
        prompt = str(body.get("prompt") or "The capital of France is")[:500]
        max_tokens = parse_int(body.get("max_new_tokens"), 64, 8, 512)
        job = self.server.jobs.start(  # type: ignore[attr-defined]
            "benchmark.py",
            {
                "model": str(folder),
                "device": device,
                "iterations": iterations,
                "warmup": warmup,
                "mode": mode,
                "prompt": prompt,
                "max_new_tokens": max_tokens,
                "num_threads": parse_int(config.load_settings().get("num_threads"), 0, 0, 256),
            },
            title=f"Бенчмарк {model_id}",
            kind="benchmark",
        )
        self._send_json({"ok": True, "job": job.to_dict(with_logs=False)})

    def api_benchmarks(self, _query=None):
        self._send_json({"history": models.benchmark_history()})

    def api_convert(self, body):
        repo = str(body.get("repo") or "").strip().strip("/")
        if not repo or repo.count("/") != 1:
            raise ApiError("Укажите модель в формате organization/model.")
        task = str(body.get("task") or "auto")
        if task == "auto":
            task = "text-generation-with-past"
            try:
                detail = hf.model_detail(repo)
                tag = (detail.get("pipeline_tag") or "").lower()
                task = {
                    "text-generation": "text-generation-with-past",
                    "text2text-generation": "text2text-generation",
                    "image-classification": "image-classification",
                    "object-detection": "object-detection",
                    "feature-extraction": "feature-extraction",
                    "automatic-speech-recognition": "automatic-speech-recognition",
                    "image-to-image": "image-to-image",
                    "text-to-image": "text-to-image",
                }.get(tag, "text-generation-with-past")
            except Exception as exc:
                log(f"convert task autodetect failed: {exc}")
        allowed_tasks = {
            "auto",
            "text-generation-with-past",
            "text-generation",
            "image-classification",
            "object-detection",
            "feature-extraction",
            "automatic-speech-recognition",
            "text2text-generation",
            "image-to-image",
            "text-to-image",
        }
        if task not in allowed_tasks:
            raise ApiError("Неизвестная задача конвертации.")
        weight = str(body.get("weight_format") or "int4")
        if weight not in ("fp32", "fp16", "int8", "int4"):
            raise ApiError("Неизвестный формат весов.")
        settings = config.load_settings()
        job = self.server.jobs.start(  # type: ignore[attr-defined]
            "convert.py",
            {
                "repo": repo,
                "task": task,
                "weight_format": weight,
                "trust_remote_code": bool(body.get("trust_remote_code")),
                "token": settings.get("hf_token") or "",
                "proxy": settings.get("proxy") or "",
                "output_name": str(body.get("output_name") or "")[:120],
            },
            title=f"Конвертация {repo.split('/')[-1]}",
            kind="convert",
        )
        self._send_json({"ok": True, "job": job.to_dict(with_logs=False)})

    def api_install(self, body):
        components = body.get("components") or []
        if not isinstance(components, list):
            raise ApiError("Некорректный список компонентов.")
        allowed = {"runtime", "genai", "convert"}
        components = [c for c in components if c in allowed]
        if not components:
            raise ApiError("Не выбрано ни одного компонента.")
        job = self.server.jobs.start(  # type: ignore[attr-defined]
            "install.py",
            {"components": components, "proxy": config.load_settings().get("proxy") or ""},
            title="Установка компонентов",
            kind="install",
        )
        self._send_json({"ok": True, "job": job.to_dict(with_logs=False)})

    def api_logs(self, query):
        limit = parse_int((query.get("limit") or ["300"])[0], 300, 20, 1000)
        lines: list[str] = []
        for name in ("studio.log", "bootstrap.log"):
            path = config.LOGS_DIR / name
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8", errors="replace") as handle:
                        content = handle.readlines()[-limit:]
                    if content:
                        lines.append(f"===== {name} =====")
                        lines.extend(line.rstrip("\n") for line in content)
                except OSError:
                    pass
        self._send_json({"ok": True, "log": "\n".join(lines[-limit * 2 :])})

    def api_open_folder(self, body):
        target = str(body.get("target") or "models")
        mapping = {
            "models": config.models_dir(),
            "logs": config.LOGS_DIR,
            "runtime": config.RUNTIME_DIR,
            "base": config.BASE_DIR,
        }
        path = mapping.get(target)
        if not path:
            raise ApiError("Неизвестная папка.")
        path.mkdir(parents=True, exist_ok=True)
        open_folder(path)
        self._send_json({"ok": True, "path": str(path)})

    def api_shutdown(self, _body):
        self._send_json({"ok": True})
        log("shutdown requested from UI")
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    # ------------------------------------------------------------------- chat
    def _sse_worker(self, worker: str, payload: dict, cleanup_paths=(), log_prefix="stream"):
        """Run a worker and relay its JSON events as Server-Sent Events."""
        token = util.timestamp_slug() + "-" + str(int(time.time() * 1000))[-6:]
        args_path = config.TMP_DIR / f"{log_prefix}-{token}.json"
        stop_path = config.TMP_DIR / f"{log_prefix}-{token}.stop"
        payload["_stop_file"] = str(stop_path)
        util.atomic_write_json(args_path, payload)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(config.APP_DIR)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        proc = None
        headers_sent = False
        try:
            proc = subprocess.Popen(
                [config.python_executable(), str(config.APP_DIR / "workers" / worker), str(args_path)],
                cwd=str(config.BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                **_hidden_kwargs(),
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.close_connection = True
            self.end_headers()
            headers_sent = True
            self.wfile.write(b": stream\n\n")
            self.wfile.flush()
            assert proc.stdout is not None
            disconnected = False
            for raw in proc.stdout:
                line = raw.strip()
                if not line.startswith("@@JSON@@"):
                    if line:
                        log(f"{log_prefix}: " + line, 10)
                    continue
                data = line[len("@@JSON@@") :]
                try:
                    self.wfile.write(("data: " + data + "\n\n").encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    disconnected = True
                    break
            if not disconnected and proc.poll() is None:
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
        except (BrokenPipeError, ConnectionResetError):
            log(f"{log_prefix} stream disconnected")
        except Exception as exc:
            log(f"{log_prefix} stream error: {exc}", 30)
            if not headers_sent:
                raise ApiError(f"Не удалось запустить модель: {exc}", 500) from exc
        finally:
            if proc and proc.poll() is None:
                try:
                    stop_path.write_text("1", encoding="utf-8")
                except OSError:
                    pass
                time.sleep(0.2)
                if proc.poll() is None:
                    if config.IS_WINDOWS:
                        subprocess.run(
                            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                            capture_output=True,
                            **_hidden_kwargs(),
                        )
                    else:
                        proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            for path in (args_path, stop_path, *cleanup_paths):
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass

    def api_chat(self, body):
        model_id = str(body.get("model_id") or "")
        folder = find_model_dir(model_id)
        settings = config.load_settings()
        device = validate_device(str(body.get("device") or ""), settings)
        threads = parse_int(settings.get("num_threads"), 0, 0, 256)
        messages = body.get("messages") or []
        if not isinstance(messages, list) or not messages:
            raise ApiError("Пустой диалог.")
        clean = []
        for message in messages[-24:]:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = str(message.get("content") or "")[:20000]
            if role in ("user", "assistant") and content.strip():
                clean.append({"role": role, "content": content})
        if not clean:
            raise ApiError("Пустой диалог.")
        params = body.get("params") or {}
        payload = {
            "model": str(folder),
            "device": device,
            "num_threads": threads,
            "messages": clean,
            "system": str(body.get("system") or "")[:8000],
            "params": {
                "max_new_tokens": parse_int(params.get("max_new_tokens"), 512, 16, 4096),
                "temperature": parse_float(params.get("temperature"), 0.7, 0.0, 2.0),
                "top_p": parse_float(params.get("top_p"), 0.95, 0.05, 1.0),
                "top_k": parse_int(params.get("top_k"), 40, 1, 200),
                "repetition_penalty": parse_float(params.get("repetition_penalty"), 1.05, 0.8, 2.0),
            },
        }
        self._sse_worker("chat.py", payload, log_prefix="chat")

    def api_vlm(self, body):
        model_id = str(body.get("model_id") or "")
        folder = find_model_dir(model_id)
        raw_image = str(body.get("image") or "")
        if not raw_image:
            raise ApiError("Не передано изображение.")
        if raw_image.startswith("data:"):
            try:
                raw_image = raw_image.split(",", 1)[1]
            except IndexError as exc:
                raise ApiError("Некорректный формат изображения.") from exc
        if len(raw_image) > 30 * 1024 * 1024:
            raise ApiError("Изображение слишком большое (максимум ~20 МБ).", 413)
        try:
            image_bytes = base64.b64decode(raw_image, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise ApiError("Не удалось декодировать изображение.") from exc
        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            raise ApiError("Введите вопрос к изображению.")
        settings = config.load_settings()
        device = validate_device(str(body.get("device") or ""), settings)
        config.TMP_DIR.mkdir(parents=True, exist_ok=True)
        image_path = config.TMP_DIR / f"vlm-{int(time.time()*1000)}.img"
        image_path.write_bytes(image_bytes)
        params = body.get("params") or {}
        payload = {
            "model": str(folder),
            "device": device,
            "num_threads": parse_int(settings.get("num_threads"), 0, 0, 256),
            "image": str(image_path),
            "prompt": prompt[:8000],
            "system": str(body.get("system") or "")[:8000],
            "params": {
                "max_new_tokens": parse_int(params.get("max_new_tokens"), 512, 16, 4096),
                "temperature": parse_float(params.get("temperature"), 0.4, 0.0, 2.0),
                "top_p": parse_float(params.get("top_p"), 0.9, 0.05, 1.0),
                "top_k": parse_int(params.get("top_k"), 40, 1, 200),
                "repetition_penalty": parse_float(params.get("repetition_penalty"), 1.05, 0.8, 2.0),
            },
        }
        try:
            self._sse_worker("vlm.py", payload, cleanup_paths=(image_path,), log_prefix="vlm")
        finally:
            try:
                image_path.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------------ image
    def api_image(self, body):
        model_id = str(body.get("model_id") or "")
        folder = find_model_dir(model_id)
        raw_image = str(body.get("image") or "")
        if not raw_image:
            raise ApiError("Не передано изображение.")
        if raw_image.startswith("data:"):
            try:
                raw_image = raw_image.split(",", 1)[1]
            except IndexError as exc:
                raise ApiError("Некорректный формат изображения.") from exc
        if len(raw_image) > 30 * 1024 * 1024:
            raise ApiError("Изображение слишком большое (максимум ~20 МБ).", 413)
        try:
            image_bytes = base64.b64decode(raw_image, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise ApiError("Не удалось декодировать изображение.") from exc
        config.TMP_DIR.mkdir(parents=True, exist_ok=True)
        image_path = config.TMP_DIR / f"image-{int(time.time()*1000)}.img"
        image_path.write_bytes(image_bytes)
        task = str(body.get("task") or "auto")
        if task not in ("auto", "classify", "detect"):
            task = "auto"
        device = validate_device(str(body.get("device") or ""), config.load_settings())
        args_path = config.TMP_DIR / f"image-{int(time.time()*1000)}.json"
        util.atomic_write_json(
            args_path,
            {
                "model": str(folder),
                "image": str(image_path),
                "task": task,
                "top_k": parse_int(body.get("top_k"), 5, 1, 20),
                "threshold": parse_float(body.get("threshold"), 0.3, 0.05, 0.95),
                "device": device,
                "num_threads": parse_int(config.load_settings().get("num_threads"), 0, 0, 256),
            },
        )
        try:
            proc = subprocess.run(
                [config.python_executable(), str(config.APP_DIR / "workers" / "image_infer.py"), str(args_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                env={**os.environ, "PYTHONPATH": str(config.APP_DIR), "PYTHONIOENCODING": "utf-8"},
                cwd=str(config.BASE_DIR),
                **_hidden_kwargs(),
            )
            result = None
            error = ""
            for line in (proc.stdout or "").splitlines():
                if line.startswith("@@JSON@@"):
                    try:
                        event = json.loads(line[len("@@JSON@@") :])
                    except Exception:
                        continue
                    if event.get("event") == "result":
                        result = event.get("data")
                    elif event.get("event") == "error":
                        error = str(event.get("message") or "")
            if result is None:
                tail = (proc.stderr or "").strip().splitlines()[-4:]
                message = error or "Модель не вернула результат."
                if tail and not error:
                    message += "\n" + "\n".join(tail)
                raise ApiError(message, 500)
            self._send_json({"ok": True, **result})
        except subprocess.TimeoutExpired as exc:
            raise ApiError("Инференс занял слишком много времени.", 504) from exc
        finally:
            for path in (args_path, image_path):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass


def validate_device(requested: str, settings: dict) -> str:
    value = requested or settings.get("default_device") or "CPU"
    if not re.match(r"^(CPU|GPU(\.\d+)?|NPU(\.\d+)?|AUTO)$", value):
        return "CPU"
    return value


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        try:
            log(f"connection error from {client_address}: {traceback.format_exc()}", 30)
        except Exception:
            pass

    def __init__(self, address, handler, jobs: JobManager):
        super().__init__(address, handler)
        self.jobs = jobs
        self.last_activity = time.time()
        self.started_at = time.time()


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def existing_server() -> dict | None:
    path = config.RUNTIME_DIR / "server.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        port = int(data.get("port"))
    except Exception:
        return None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("app") == config.APP_NAME:
            return data
    except Exception:
        return None
    return None


def watchdog(server: StudioServer, stop_event: threading.Event) -> None:
    while not stop_event.wait(120):
        idle = time.time() - server.last_activity
        if idle > 120 * 60 and server.jobs.active_count() == 0:
            log("idle shutdown")
            server.shutdown()
            return


def on_job_finished(job) -> None:
    if job.kind == "install" and job.status == "done":
        system.invalidate_probe()
    if job.kind == "benchmark" and job.status == "done" and isinstance(job.result, dict):
        result = dict(job.result)
        result["job_id"] = job.id
        models.add_benchmark_result(result)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    config.ensure_dirs()
    config.apply_env()
    setup_logging(args.debug)
    log(f"OpenVINO Studio {config.APP_VERSION} starting from {config.BASE_DIR}")

    if not args.port:
        running = existing_server()
        if running:
            url = f"http://127.0.0.1:{running['port']}/"
            log(f"already running: {url}")
            if not args.no_open:
                open_app_window(url)
            return 0

    jobs = JobManager(on_finished=on_job_finished)
    port = args.port
    if not port:
        port = 8765
        for candidate in range(8765, 8790):
            if port_available(candidate):
                port = candidate
                break
        else:
            log("no free port", 40)
            return 1

    try:
        server = StudioServer(("127.0.0.1", port), StudioHandler, jobs)
    except OSError:
        if not args.port:
            for candidate in range(port + 1, port + 25):
                if port_available(candidate):
                    server = StudioServer(("127.0.0.1", candidate), StudioHandler, jobs)
                    port = candidate
                    break
            else:
                raise
        else:
            raise

    url = f"http://127.0.0.1:{port}/"
    util.atomic_write_json(
        config.RUNTIME_DIR / "server.json",
        {
            "pid": os.getpid(),
            "port": port,
            "url": url,
            "version": config.APP_VERSION,
            "started_at": util.now_iso(),
        },
    )
    log(f"listening on {url}")

    stop_event = threading.Event()
    threading.Thread(target=watchdog, args=(server, stop_event), daemon=True).start()
    if not args.no_open:
        threading.Timer(0.5, lambda: open_app_window(url)).start()

    def _stop(_signum=None, _frame=None):
        stop_event.set()
        jobs.shutdown()
        threading.Thread(target=server.shutdown, daemon=True).start()

    try:
        import signal

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
    except Exception:
        pass

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        stop_event.set()
        jobs.shutdown()
        try:
            server.server_close()
        except Exception:
            pass
        try:
            current = json.loads((config.RUNTIME_DIR / "server.json").read_text(encoding="utf-8"))
            if current.get("pid") == os.getpid():
                (config.RUNTIME_DIR / "server.json").unlink(missing_ok=True)
        except Exception:
            pass
        log("server stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
