"""Background jobs running isolated worker processes."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from . import config
from .util import atomic_write_json, human_size, log, now_iso, read_json

WORKERS_DIR = config.APP_DIR / "workers"
MAX_LOG_LINES = 350


def _hidden_kwargs() -> dict:
    kwargs: dict = {}
    if config.IS_WINDOWS:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    return kwargs


class Job:
    def __init__(self, kind: str, title: str, worker: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self.worker = worker
        self.status = "queued"
        self.progress = 0.0
        self.detail = "В очереди"
        self.logs: list[str] = []
        self.result = None
        self.error = ""
        self.created_at = time.time()
        self.finished_at: float | None = None
        self.cancel_requested = False
        self.process: subprocess.Popen | None = None
        self.args_path: Path | None = None
        self.stop_path: Path | None = None
        self.lock = threading.Lock()

    def add_log(self, line: str) -> None:
        line = (line or "").rstrip("\n\r")
        if not line:
            return
        if len(line) > 4000:
            line = line[:4000] + "…"
        with self.lock:
            self.logs.append(line)
            if len(self.logs) > MAX_LOG_LINES:
                del self.logs[: len(self.logs) - MAX_LOG_LINES]

    def set_progress(self, value, detail: str | None = None) -> None:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        self.progress = max(0.0, min(1.0, value))
        if detail:
            self.detail = str(detail)[:400]

    def to_dict(self, with_logs: bool = True) -> dict:
        data = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "progress": round(self.progress, 4),
            "detail": self.detail,
            "error": self.error,
            "result": self.result,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "elapsed": round((self.finished_at or time.time()) - self.created_at, 1),
            "cancellable": self.status in ("queued", "running"),
        }
        if with_logs:
            with self.lock:
                data["logs"] = list(self.logs[-200:])
        return data


class JobManager:
    def __init__(self, on_finished=None):
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.on_finished = on_finished
        self._cleanup_old_args()

    def _cleanup_old_args(self) -> None:
        cutoff = time.time() - 7 * 86400
        for path in config.JOBS_DIR.glob("*.json"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass

    def start(self, worker: str, payload: dict, title: str, kind: str) -> Job:
        worker_path = WORKERS_DIR / worker
        if not worker_path.exists():
            raise FileNotFoundError(f"Воркер не найден: {worker}")
        job = Job(kind, title, worker)
        job.stop_path = config.JOBS_DIR / f"{job.id}.stop"
        job.args_path = config.JOBS_DIR / f"{job.id}.json"
        payload = dict(payload)
        payload["_job_id"] = job.id
        payload["_stop_file"] = str(job.stop_path)
        atomic_write_json(job.args_path, payload)
        with self.lock:
            self.jobs[job.id] = job
        thread = threading.Thread(target=self._execute, args=(job, worker_path), daemon=True)
        thread.start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def list(self, limit: int = 40) -> list[dict]:
        with self.lock:
            jobs = sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]
        return [job.to_dict() for job in jobs]

    def active_count(self) -> int:
        with self.lock:
            return sum(1 for j in self.jobs.values() if j.status in ("queued", "running"))

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job or job.status not in ("queued", "running"):
            return False
        job.cancel_requested = True
        job.detail = "Остановка…"
        try:
            if job.stop_path:
                job.stop_path.write_text("1", encoding="utf-8")
        except OSError:
            pass
        self._terminate(job)
        return True

    def shutdown(self) -> None:
        with self.lock:
            jobs = list(self.jobs.values())
        for job in jobs:
            if job.status in ("queued", "running"):
                job.cancel_requested = True
                self._terminate(job)

    def _terminate(self, job: Job) -> None:
        proc = job.process
        if not proc or proc.poll() is not None:
            return
        try:
            if config.IS_WINDOWS:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                    **_hidden_kwargs(),
                )
            else:
                proc.terminate()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _execute(self, job: Job, worker_path: Path) -> None:
        env = os.environ.copy()
        config.apply_env()
        env.update(os.environ)
        env["PYTHONPATH"] = str(config.APP_DIR) + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["OVS_BASE"] = str(config.BASE_DIR)
        env["OVS_MODELS"] = str(config.models_dir())
        env["OVS_RUNTIME"] = str(config.RUNTIME_DIR)
        env["OVS_CA_BUNDLE"] = str(config.APP_DIR.parent / "app" / "assets" / "cacert.pem")
        cmd = [config.python_executable(), str(worker_path), str(job.args_path)]
        log(f"job {job.id} start: {job.worker}")
        with job.lock:
            job.status = "running"
            job.detail = "Запуск…"
        try:
            proc = subprocess.Popen(
                cmd,
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
            job.process = proc
            assert proc.stdout is not None
            for raw in proc.stdout:
                self._handle_line(job, raw)
            code = proc.wait()
        except Exception as exc:
            code = -1
            job.error = f"Не удалось запустить задачу: {exc}"
            log(f"job {job.id} spawn error: {exc}")
        finally:
            if job.args_path:
                try:
                    job.args_path.unlink()
                except OSError:
                    pass
            if job.stop_path:
                try:
                    job.stop_path.unlink()
                except OSError:
                    pass

        job.finished_at = time.time()
        if job.cancel_requested:
            job.status = "cancelled"
            job.detail = "Отменено"
        elif code == 0 and not job.error:
            job.status = "done"
            job.progress = 1.0
            job.detail = "Готово"
        else:
            job.status = "error"
            if not job.error:
                tail = [ln for ln in job.logs if not ln.startswith("@@")][-6:]
                job.error = "Задача завершилась с ошибкой." + (("\n" + "\n".join(tail)) if tail else "")
            job.detail = "Ошибка"
        log(f"job {job.id} finished: {job.status} code={code}")
        job.process = None
        if self.on_finished:
            try:
                self.on_finished(job)
            except Exception as exc:
                log(f"on_finished error: {exc}")

    def _handle_line(self, job: Job, raw: str) -> None:
        line = raw.rstrip("\n\r")
        if not line:
            return
        if line.startswith("@@JSON@@"):
            try:
                event = json.loads(line[len("@@JSON@@") :])
            except Exception:
                job.add_log(line)
                return
            kind = event.get("event")
            if kind == "progress":
                job.set_progress(event.get("value", 0), event.get("detail"))
            elif kind == "result":
                job.result = event.get("data")
                if event.get("detail"):
                    job.detail = str(event["detail"])
            elif kind == "error":
                job.error = str(event.get("message") or "Ошибка")
                job.add_log(job.error)
            elif kind == "log":
                job.add_log(str(event.get("message") or ""))
            elif kind == "detail":
                job.detail = str(event.get("detail") or job.detail)
            else:
                job.add_log(line)
        else:
            job.add_log(line)
