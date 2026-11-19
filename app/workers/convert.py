"""Convert a Hugging Face model to OpenVINO IR with Optimum Intel."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


def emit(event: str, **data) -> None:
    print("@@JSON@@" + json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def log(message: str) -> None:
    emit("log", message=str(message).rstrip())


def human_size(num: float) -> str:
    units = ["Б", "КБ", "МБ", "ГБ"]
    idx = 0
    num = float(num or 0)
    while num >= 1024 and idx < len(units) - 1:
        num /= 1024.0
        idx += 1
    return f"{num:.0f} {units[idx]}" if idx == 0 else f"{num:.2f} {units[idx]}".replace(".00", "")


def safe_name(name: str) -> str:
    name = name.replace("/", "__").replace("\\", "__")
    for ch in '<>:"|?*':
        name = name.replace(ch, "_")
    return name.strip(" .")[:110] or "model"


def main() -> None:
    args = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    repo = (args.get("repo") or "").strip().strip("/")
    task = args.get("task") or "text-generation-with-past"
    weight_format = args.get("weight_format") or "int4"
    trust = bool(args.get("trust_remote_code"))
    token = (args.get("token") or "").strip()
    proxy = (args.get("proxy") or "").strip()
    models_root = Path(os.environ.get("OVS_MODELS") or (Path.cwd() / "models"))

    if not repo or repo.count("/") != 1:
        raise SystemExit("Укажите модель в формате organization/model.")
    if task == "auto":
        task = "text-generation-with-past"
    if importlib.util.find_spec("optimum") is None:
        emit(
            "error",
            message=(
                "Не установлен Optimum Intel. Откройте «Инструменты» → «Компоненты» "
                "и установите «Конвертация и квантование»."
            ),
        )
        return
    if importlib.util.find_spec("torch") is None and task.startswith(("text", "image")):
        log("Внимание: PyTorch не найден. Для большинства моделей он нужен.")

    out_name = safe_name(args.get("output_name") or f"{repo}-{weight_format}-ov")
    out_dir = models_root / out_name
    if out_dir.exists() and any(out_dir.iterdir()):
        suffix = 2
        while (models_root / f"{out_name}-{suffix}").exists():
            suffix += 1
        out_name = f"{out_name}-{suffix}"
        out_dir = models_root / out_name
    out_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["HF_HOME"] = env.get("HF_HOME", str(Path(os.environ["OVS_RUNTIME"]) / "hf"))
    if token:
        env["HF_TOKEN"] = token
        env["HUGGING_FACE_HUB_TOKEN"] = token
    if proxy:
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy

    module_ok = importlib.util.find_spec("optimum.commands.optimum_cli") is not None
    if module_ok:
        base_cmd = [sys.executable, "-m", "optimum.commands.optimum_cli"]
    else:
        executable = shutil.which("optimum-cli")
        if not executable:
            for name in ("optimum-cli.exe", "optimum-cli"):
                candidate = Path(sys.executable).parent / name
                if candidate.exists():
                    executable = str(candidate)
                    break
        if not executable:
            emit("error", message="Не найден optimum-cli. Переустановите компонент «Конвертация».")
            return
        base_cmd = [executable]
    cmd = [
        *base_cmd,
        "export",
        "openvino",
        "--model",
        repo,
        "--task",
        task,
        "--weight-format",
        weight_format,
        str(out_dir),
    ]
    if trust:
        cmd.append("--trust-remote-code")
    emit("detail", detail=f"Экспорт {repo} → {weight_format}")
    log("$ " + " ".join(cmd))
    started = time.time()
    proc = None

    def terminate(_signum, _frame):
        if proc and proc.poll() is None:
            proc.terminate()
        sys.exit(1)

    try:
        signal.signal(signal.SIGTERM, terminate)
    except Exception:
        pass

    last_progress = 0.0
    try:
        proc = subprocess.Popen(
            cmd,
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
            if not line.strip():
                continue
            log(line)
            match = re.search(r"(\d{1,3})%", line)
            if match:
                value = min(0.94, max(0.05, int(match.group(1)) / 100.0))
                if value - last_progress >= 0.01:
                    last_progress = value
                    emit("progress", value=value, detail=f"Конвертация… {match.group(1)}%")
            if "Loading" in line or "Downloading" in line:
                emit("detail", detail="Загрузка исходной модели…")
        code = proc.wait()
    except Exception as exc:
        emit("error", message=f"Не удалось запустить конвертацию: {exc}")
        return

    if code != 0:
        try:
            meta = {"incomplete": True, "source_repo": repo, "task": task, "weight_format": weight_format}
            (out_dir / ".ovstudio.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        emit(
            "error",
            message=(
                "Optimum завершился с ошибкой. Проверьте журнал: возможно, модель не поддерживает "
                "выбранную задачу или нужен --trust-remote-code."
            ),
        )
        return

    has_ir = any(p.suffix.lower() == ".xml" and "tokenizer" not in p.name.lower() for p in out_dir.rglob("*.xml"))
    if not has_ir:
        emit("error", message="Экспорт завершился, но IR-файлы не найдены. Смотрите журнал.")
        return
    size = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    meta = {
        "source": "optimum",
        "source_repo": repo,
        "repo_id": repo,
        "task": task,
        "weight_format": weight_format,
        "converted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "incomplete": False,
        "size": size,
        "display_name": repo.split("/")[-1] + f" ({weight_format})",
    }
    (out_dir / ".ovstudio.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    emit("progress", value=1.0, detail="Конвертация завершена")
    emit(
        "result",
        data={
            "path": str(out_dir),
            "name": out_name,
            "size": size,
            "size_label": human_size(size),
            "repo": repo,
            "seconds": round(time.time() - started, 1),
        },
    )
    log(f"Готово: {out_dir} ({human_size(size)})")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        emit("error", message=str(exc))
        raise
