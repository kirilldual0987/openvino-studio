"""Embedded Chromium window (Qt WebEngine) for OpenVINO Studio.

This is the primary desktop shell on Windows, macOS and Linux: it bundles its
own browser engine, so no external browser and no WebView2/GTK dependency.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RUNTIME = BASE / "runtime"
LOG = RUNTIME / "logs" / "window.log"
READY = RUNTIME / "window.ready"
STORAGE = RUNTIME / "webview"


def log(message: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/api/ping", timeout=1.5) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.35)
    return False


def shutdown(url: str) -> None:
    try:
        request = urllib.request.Request(
            url.rstrip("/") + "/api/shutdown",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(request, timeout=3).read()
        log("shutdown requested")
    except Exception as exc:
        log(f"shutdown failed: {exc}")


def main() -> int:
    if len(sys.argv) < 2:
        log("no URL")
        return 2
    url = sys.argv[1]
    log(f"starting Qt window for {url}")
    if not wait_for_server(url):
        log("server did not become ready")
        return 3
    try:
        from PySide6.QtCore import QUrl, QTimer
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication, QMainWindow
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except Exception as exc:
        log(f"PySide6 import failed: {exc}")
        return 4

    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "studio.openvino.bykirilldual0987"
            )
        except Exception:
            pass

    try:
        STORAGE.mkdir(parents=True, exist_ok=True)
        (STORAGE / "cache").mkdir(parents=True, exist_ok=True)
        (STORAGE / "storage").mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    app = QApplication(sys.argv[:1])
    app.setApplicationName("OpenVINO Studio")
    app.setOrganizationName("ByKirilldual0987")

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.url = url
            self.ready_written = False
            self.setWindowTitle("OpenVINO Studio")
            screen = QApplication.primaryScreen()
            area = screen.availableGeometry() if screen else None
            width = min(1400, max(980, area.width() - 80)) if area else 1400
            height = min(900, max(640, area.height() - 80)) if area else 900
            self.resize(width, height)
            self.setMinimumSize(980, 640)
            icon_path = BASE / "app" / "assets" / "logo-128.png"
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
            self.profile = QWebEngineProfile("OpenVINOStudio", self)
            try:
                self.profile.setCachePath(str(STORAGE / "cache"))
                self.profile.setPersistentStoragePath(str(STORAGE / "storage"))
                self.profile.setPersistentCookiesPolicy(
                    QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
                )
            except Exception as exc:
                log(f"profile paths failed: {exc}")
            self.view = QWebEngineView(self)
            self.page = QWebEnginePage(self.profile, self.view)
            self.view.setPage(self.page)
            self.view.setUrl(QUrl(url))
            self.setCentralWidget(self.view)
            self.view.loadFinished.connect(self.on_loaded)
            self.view.titleChanged.connect(self.on_title)

        def on_title(self, title: str) -> None:
            if title:
                self.setWindowTitle(title if "OpenVINO Studio" in title else f"{title} — OpenVINO Studio")

        def on_loaded(self, ok: bool) -> None:
            log(f"page load finished: {ok}")
            if not ok:
                self.close()
                return
            if not self.ready_written:
                try:
                    READY.parent.mkdir(parents=True, exist_ok=True)
                    READY.write_text(self.url, encoding="utf-8")
                    self.ready_written = True
                    log("window ready")
                except Exception as exc:
                    log(f"ready marker failed: {exc}")

        def closeEvent(self, event) -> None:
            log("window closing")
            try:
                READY.unlink(missing_ok=True)
            except OSError:
                pass
            event.accept()

    try:
        READY.unlink(missing_ok=True)
        window = MainWindow()
        window.show()
        window.raise_()
        window.activateWindow()
        code = app.exec()
    except Exception as exc:
        log(f"window failed: {exc}\n{traceback.format_exc()}")
        return 5
    log("window closed")
    shutdown(url)
    return code


if __name__ == "__main__":
    sys.exit(main())
