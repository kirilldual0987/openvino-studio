"""Install optional Python components into the application's venv."""
from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import sys
import time
from pathlib import Path

COMPONENTS = {
    "runtime": ["openvino", "pillow", "numpy"],
    "genai": ["openvino-genai"],
    "convert": ["optimum-intel[openvino]", "nncf", "torch", "transformers", "sentencepiece"],
}


def emit(event: str, **data) -> None:
    print("@@JSON@@" + json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def log(message: str) -> None:
    emit("log", message=str(message).rstrip())


def version(dist: str) -> str:
    try:
        return importlib.metadata.version(dist)
    except Exception:
        return ""


def main() -> None:
    args = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    components = args.get("components") or []
    packages: list[str] = []
    for component in components:
        for package in COMPONENTS.get(component, []):
            if package not in packages:
                packages.append(package)
    if not packages:
        emit("error", message="Не выбрано ни одного компонента.")
        return

    emit("detail", detail="Проверка pip…")
    log("Пакеты: " + ", ".join(packages))
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--no-input",
        "--disable-pip-version-check",
        "--progress-bar",
        "off",
        "--no-warn-script-location",
        *packages,
    ]
    log("$ " + " ".join(command))
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PIP_NO_INPUT"] = "1"
    proxy = str(args.get("proxy") or "").strip()
    if proxy:
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy
    started = time.time()
    lines = 0
    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            lines += 1
            log(line)
            if lines % 4 == 0:
                value = min(0.9, 0.08 + lines * 0.004)
                emit("progress", value=value, detail="Установка пакетов…")
        code = proc.wait()
    except Exception as exc:
        emit("error", message=f"Не удалось запустить pip: {exc}")
        return
    if code != 0:
        emit(
            "error",
            message=(
                "pip завершился с ошибкой. Проверьте интернет и свободное место, "
                "затем повторите установку. Подробности — в журнале."
            ),
        )
        return
    installed = {
        "openvino": version("openvino"),
        "openvino-genai": version("openvino-genai"),
        "optimum-intel": version("optimum-intel"),
        "nncf": version("nncf"),
        "torch": version("torch"),
        "pillow": version("pillow"),
        "numpy": version("numpy"),
    }
    emit("progress", value=1.0, detail="Компоненты установлены")
    emit(
        "result",
        data={
            "installed": installed,
            "seconds": round(time.time() - started, 1),
        },
    )
    log("Установка завершена.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit("error", message=str(exc))
        raise
