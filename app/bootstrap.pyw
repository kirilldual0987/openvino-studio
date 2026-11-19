"""Silent first-run bootstrap for OpenVINO Studio (Windows).

Creates a private virtual environment on the same drive and starts the local
UI server. There is no console: the window below appears only on the first run.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
import sys
import time
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
APP = BASE / "app"
RUNTIME = BASE / "runtime"
LOGS = RUNTIME / "logs"
VENV = RUNTIME / "venv"
LOG_FILE = LOGS / "bootstrap.log"
IS_WINDOWS = os.name == "nt"
MIN_PYTHON = (3, 10)


def log(message: str) -> None:
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 1_000_000:
            LOG_FILE.write_text("", encoding="utf-8")
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


def hidden_kwargs() -> dict:
    if not IS_WINDOWS:
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 0
    return {"startupinfo": info, "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}


def console_python(exe: Path | None = None) -> Path:
    """pythonw.exe cannot always report pip errors; use python.exe for setup."""
    exe = Path(exe or sys.executable)
    if IS_WINDOWS and exe.name.lower() == "pythonw.exe":
        candidate = exe.with_name("python.exe")
        if candidate.exists():
            return candidate
    return exe


def venv_python() -> Path:
    if IS_WINDOWS:
        for name in ("pythonw.exe", "python.exe"):
            candidate = VENV / "Scripts" / name
            if candidate.exists():
                return candidate
        return VENV / "Scripts" / "pythonw.exe"
    for name in ("python3", "python"):
        candidate = VENV / "bin" / name
        if candidate.exists():
            return candidate
    return VENV / "bin" / "python3"


def show_error(message: str) -> None:
    log("ERROR: " + message)
    full = message + "\n\nПодробности: runtime\\logs\\bootstrap.log"
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("OpenVINO Studio", full)
        root.destroy()
        return
    except Exception:
        pass
    if IS_WINDOWS:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, full, "OpenVINO Studio", 0x10)
        except Exception:
            pass
    elif sys.platform == "darwin":
        try:
            import json

            script = 'display alert "OpenVINO Studio" message ' + json.dumps(full) + " as critical"
            subprocess.run(["osascript", "-e", script], timeout=30, **hidden_kwargs())
        except Exception:
            pass
    else:
        for cmd in (
            ["zenity", "--error", "--title=OpenVINO Studio", "--text=" + full],
            ["kdialog", "--title", "OpenVINO Studio", "--error", full],
        ):
            try:
                subprocess.run(cmd, timeout=30, **hidden_kwargs())
                break
            except Exception:
                continue


class Splash:
    def __init__(self, status: str):
        import tkinter as tk

        self.tk = tk
        self.root = tk.Tk()
        self.root.title("OpenVINO Studio")
        self.root.configure(bg="#121318")
        self.root.resizable(False, False)
        width, height = 540, 340
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        try:
            icon = tk.PhotoImage(file=str(APP / "assets" / "logo-128.png"))
            self.root.iconphoto(True, icon)
            self._icon = icon
        except Exception:
            pass

        logo = None
        try:
            logo = tk.PhotoImage(file=str(APP / "assets" / "logo-128.png"))
        except Exception:
            pass
        if logo is not None:
            self._logo = logo
            tk.Label(self.root, image=logo, bg="#121318", bd=0).pack(pady=(34, 12))
        tk.Label(
            self.root,
            text="OpenVINO Studio",
            bg="#121318",
            fg="#e4e1e9",
            font=("Segoe UI", 19, "bold") if IS_WINDOWS else ("Helvetica Neue", 19, "bold"),
        ).pack()
        tk.Label(
            self.root,
            text="Первый запуск: готовим окружение на внешнем диске",
            bg="#121318",
            fg="#c7c5d0",
            font=("Segoe UI", 10) if IS_WINDOWS else ("Helvetica Neue", 10),
        ).pack(pady=(6, 22))
        self.status = tk.Label(
            self.root,
            text=status,
            bg="#121318",
            fg="#bac3ff",
            font=("Segoe UI", 10) if IS_WINDOWS else ("Helvetica Neue", 10),
        )
        self.status.pack()
        self.canvas = tk.Canvas(self.root, width=430, height=6, bg="#121318", highlightthickness=0, bd=0)
        self.canvas.pack(pady=(16, 0))
        self.canvas.create_rectangle(0, 1, 430, 5, fill="#32333b", outline="")
        self.bar = self.canvas.create_rectangle(0, 1, 24, 5, fill="#4a5ac9", outline="")
        self.progress = 0.05
        self.hint = tk.Label(
            self.root,
            text="Первый запуск: скачиваем движок окна. Это может занять несколько минут.",
            bg="#121318",
            fg="#90909a",
            font=("Segoe UI", 9) if IS_WINDOWS else ("Helvetica Neue", 9),
        )
        self.hint.pack(pady=(20, 0))
        self.root.update()

    def update(self, status: str, progress: float | None = None) -> None:
        try:
            self.status.config(text=status)
            if progress is not None:
                self.progress = max(0.02, min(1.0, progress))
                self.canvas.coords(self.bar, 0, 1, 430 * self.progress, 5)
            self.root.update()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self.root.destroy()
        except Exception:
            pass


def ensure_venv(splash: Splash | None = None) -> Path:
    python = venv_python()
    if python.exists():
        return python
    LOGS.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if splash:
        splash.update("Создаём изолированное окружение…", 0.2)
    setup_python = console_python()
    log(f"creating venv at {VENV} with {setup_python}")
    command = [str(setup_python), "-m", "venv", "--copies", str(VENV)]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        **hidden_kwargs(),
    )
    log(f"venv exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    if proc.returncode != 0 or not venv_python().exists():
        tail = (proc.stderr or proc.stdout or "").strip()[-1200:]
        raise RuntimeError("Не удалось создать окружение Python.\n" + tail)
    python = venv_python()
    if splash:
        splash.update("Проверяем pip…", 0.55)
    pip_python = console_python(python)
    check = subprocess.run(
        [str(pip_python), "-m", "pip", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        **hidden_kwargs(),
    )
    if check.returncode != 0:
        subprocess.run(
            [str(pip_python), "-m", "ensurepip", "--upgrade"],
            capture_output=True,
            timeout=180,
            **hidden_kwargs(),
        )
    return python


def start_server(python: Path) -> None:
    server = APP / "server.py"
    if not server.exists():
        raise RuntimeError("Не найден app/server.py. Скопируйте папку приложения целиком.")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    log(f"starting server: {python} {server}")
    kwargs = hidden_kwargs()
    proc = subprocess.Popen(
        [str(python), str(server), "--no-open"],
        cwd=str(BASE),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        env=env,
        **kwargs,
    )
    time.sleep(1.6)
    code = proc.poll()
    if code is not None and code != 0:
        tail = ""
        try:
            log_path = LOGS / "studio.log"
            if log_path.exists():
                tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-8:])
        except Exception:
            pass
        raise RuntimeError("Сервер не запустился." + (("\n" + tail) if tail else ""))


def wait_for_url(timeout: float = 30.0) -> str:
    """Wait until the local server answers and return its URL."""
    info = RUNTIME / "server.json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data = json.loads(info.read_text(encoding="utf-8"))
            port = int(data.get("port"))
            url = f"http://127.0.0.1:{port}/"
            with urllib.request.urlopen(url + "api/ping", timeout=1.0) as response:
                if response.status == 200:
                    return url
        except Exception:
            pass
        time.sleep(0.4)
    return ""


def _probe(python: Path, code: str, timeout: int = 90) -> bool:
    try:
        proc = subprocess.run(
            [str(console_python(python)), "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            **hidden_kwargs(),
        )
        return proc.returncode == 0
    except Exception:
        return False


def _pip_install(python: Path, package: str, timeout: int = 1200) -> bool:
    env = os.environ.copy()
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_NO_INPUT"] = "1"
    env["PIP_CACHE_DIR"] = str(RUNTIME / "pip-cache")
    env["TMP"] = str(RUNTIME / "tmp")
    env["TEMP"] = str(RUNTIME / "tmp")
    env["TMPDIR"] = str(RUNTIME / "tmp")
    try:
        proc = subprocess.run(
            [
                str(console_python(python)),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--no-warn-script-location",
                package,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            **hidden_kwargs(),
        )
        log(f"pip install {package} exit={proc.returncode}\n{proc.stdout[-3000:]}\n{proc.stderr[-1500:]}")
        return proc.returncode == 0
    except Exception as exc:
        log(f"pip install {package} failed: {exc}")
        return False


def ensure_embedded(python: Path, splash: "Splash | None" = None) -> list[str]:
    """Install and return the available embedded browser backends, best first."""
    backends: list[str] = []
    qt_probe = "from PySide6.QtWebEngineWidgets import QWebEngineView"
    if _probe(python, qt_probe, timeout=120):
        backends.append("qt")
    else:
        log("PySide6 WebEngine is missing, installing…")
        if splash:
            splash.update("Устанавливаем встроенный браузер (≈500 МБ)…", 0.68)
        install_env = os.environ.copy()
        install_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        install_env["PIP_NO_INPUT"] = "1"
        install_env["PIP_CACHE_DIR"] = str(RUNTIME / "pip-cache")
        install_env["TMP"] = str(RUNTIME / "tmp")
        install_env["TEMP"] = str(RUNTIME / "tmp")
        install_env["TMPDIR"] = str(RUNTIME / "tmp")
        try:
            proc = subprocess.run(
                [
                    str(console_python(python)),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--no-warn-script-location",
                    "PySide6",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
                env=install_env,
                **hidden_kwargs(),
            )
            log(f"PySide6 install exit={proc.returncode}\n{proc.stdout[-4000:]}\n{proc.stderr[-2000:]}")
        except Exception as exc:
            log(f"PySide6 install failed: {exc}")
        if _probe(python, qt_probe, timeout=180):
            backends.append("qt")

    if _probe(python, "import webview", timeout=90):
        backends.append("pywebview")
    elif not backends:
        log("pywebview is missing, installing as fallback…")
        if splash:
            splash.update("Устанавливаем запасное окно…", 0.78)
        _pip_install(python, "pywebview", timeout=600)
        if _probe(python, "import webview", timeout=90):
            backends.append("pywebview")
    return backends


def open_browser(url: str) -> bool:
    log(f"fallback browser: {url}")
    try:
        if IS_WINDOWS:
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", url], close_fds=True)
            return True
        subprocess.Popen(["xdg-open", url], close_fds=True)
        return True
    except Exception as exc:
        log(f"fallback browser failed: {exc}")
        return False


def browser_hint(url: str) -> None:
    message = (
        "OpenVINO Studio запущен, но встроенное окно не открылось.\n\n"
        f"Откройте вручную:\n{url}\n\n"
        "Ссылка сохранена в runtime\\open-in-browser.url"
    )
    log(message)
    try:
        (RUNTIME / "open-in-browser.url").write_text(
            f"[InternetShortcut]\nURL={url}\n", encoding="utf-8"
        )
    except Exception:
        pass
    try:
        if IS_WINDOWS:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "OpenVINO Studio", 0x40)
        elif sys.platform == "darwin":
            import json as _json

            subprocess.run(
                ["osascript", "-e", 'display alert "OpenVINO Studio" message ' + _json.dumps(message)],
                timeout=60,
            )
        else:
            subprocess.run(["zenity", "--info", "--title=OpenVINO Studio", "--text=" + message], timeout=60)
    except Exception:
        pass


def _wait_ready(proc, ready: Path, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ready.exists():
            return True
        if proc.poll() is not None:
            log(f"window process exited with code {proc.poll()}")
            return False
        time.sleep(0.35)
    return False


def open_window(python: Path, url: str, backends: list[str], splash: "Splash | None" = None) -> bool:
    ready = RUNTIME / "window.ready"
    for backend in backends:
        script = APP / ("window_qt.py" if backend == "qt" else "window.py")
        if not script.exists():
            continue
        try:
            ready.unlink(missing_ok=True)
        except OSError:
            pass
        log(f"launching {backend} window: {script} {url}")
        try:
            proc = subprocess.Popen(
                [str(console_python(python)), str(script), url],
                cwd=str(BASE),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                **hidden_kwargs(),
            )
        except Exception as exc:
            log(f"{backend} process failed: {exc}")
            continue
        if _wait_ready(proc, ready, timeout=40.0):
            log(f"{backend} window ready")
            return True
        log(f"{backend} window failed, trying next backend")
        try:
            if proc.poll() is None:
                proc.terminate()
                time.sleep(0.3)
                if proc.poll() is None:
                    proc.kill()
        except Exception:
            pass
    return False


def main() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    log("bootstrap started, python " + sys.version.replace("\n", " "))
    if sys.version_info < MIN_PYTHON:
        show_error(
            "Нужен Python 3.10 или новее.\n"
            f"Сейчас найден Python {sys.version_info.major}.{sys.version_info.minor}.\n"
            "Установите Python с python.org и запустите OpenVINO Studio снова."
        )
        return
    first_run = not venv_python().exists()
    splash = None
    try:
        if first_run:
            try:
                splash = Splash("Проверяем Python…")
                splash.update("Python найден, создаём окружение…", 0.12)
            except Exception as exc:
                log(f"splash unavailable: {exc}")
                splash = None
        python = ensure_venv(splash)
        backends = ensure_embedded(python, splash)
        log(f"embedded backends: {backends}")
        if splash:
            splash.update("Запускаем интерфейс…", 0.9)
        start_server(python)
        url = wait_for_url()
        if not url:
            raise RuntimeError("Сервер не ответил. Смотрите runtime\\logs\\studio.log.")
        if splash:
            splash.update("Открываем окно…", 0.96)
        if not open_window(python, url, backends, splash):
            log("embedded window unavailable")
            browser_hint(url)
        if splash:
            splash.update("Готово", 1.0)
            time.sleep(0.3)
            splash.close()
        log("bootstrap finished")
    except Exception as exc:
        log("bootstrap failed: " + repr(exc) + "\n" + traceback.format_exc())
        if splash:
            splash.close()
        show_error(str(exc))


if __name__ == "__main__":
    main()
