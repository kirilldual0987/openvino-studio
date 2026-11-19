"""Embedded desktop window for OpenVINO Studio.

Uses pywebview (Edge WebView2 on Windows, WKWebView on macOS,
WebKitGTK/Qt on Linux). Runs as a separate process so the HTTP
server can keep its own event loop.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RUNTIME = BASE / "runtime"
LOG = RUNTIME / "logs" / "window.log"
READY = RUNTIME / "window.ready"


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
        data = b"{}"
        request = urllib.request.Request(
            url.rstrip("/") + "/api/shutdown",
            data=data,
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
    log(f"starting window for {url}")
    if not wait_for_server(url):
        log("server did not become ready")
        return 3
    try:
        import webview
    except Exception as exc:
        log(f"pywebview import failed: {exc}")
        return 4

    ready_written = False

    def on_start():
        nonlocal ready_written
        try:
            READY.parent.mkdir(parents=True, exist_ok=True)
            READY.write_text(url, encoding="utf-8")
            ready_written = True
            log("window ready")
        except Exception as exc:
            log(f"ready marker failed: {exc}")

    try:
        READY.unlink(missing_ok=True)
        webview.create_window(
            "OpenVINO Studio",
            url,
            width=1360,
            height=900,
            min_size=(980, 640),
            background_color="#FBF8FF",
            text_select=True,
        )
        storage = RUNTIME / "webview"
        storage.mkdir(parents=True, exist_ok=True)
        try:
            webview.start(on_start, storage_path=str(storage), private_mode=False)
        except TypeError:
            webview.start(on_start)
    except Exception as exc:
        log(f"window failed: {exc}")
        return 5
    log("window closed")
    try:
        READY.unlink(missing_ok=True)
    except OSError:
        pass
    shutdown(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
