"""Download a Hugging Face repository into the local model library.

Uses only the standard library: resumable HTTP range downloads, no cache
duplication, no symlinks (safe on exFAT drives).
"""
from __future__ import annotations

import json
import os
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CHUNK = 1024 * 1024
USER_AGENT = "OpenVINO-Studio/1.0 (+local desktop app)"
HF_API = "https://huggingface.co/api"
HF_SITE = "https://huggingface.co"
MAX_RETRIES = 3

SKIP_SUFFIXES = (
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".mp4",
    ".pdf",
    ".gitattributes",
)
KEEP_SUFFIXES = (".xml", ".bin", ".model", ".json", ".txt", ".tiktoken", ".jinja", ".py", ".yaml", ".yml")


def emit(event: str, **data) -> None:
    print("@@JSON@@" + json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def log(message: str) -> None:
    emit("log", message=message)


def human_size(num: float) -> str:
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
    idx = 0
    num = float(num or 0)
    while num >= 1024 and idx < len(units) - 1:
        num /= 1024.0
        idx += 1
    return f"{num:.0f} {units[idx]}" if idx == 0 else f"{num:.2f} {units[idx]}".replace(".00", "")


def human_eta(seconds: float) -> str:
    if seconds <= 0 or seconds > 86400 * 3:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} с"
    if seconds < 3600:
        return f"{seconds // 60} мин"
    return f"{seconds // 3600} ч {(seconds % 3600) // 60:02d} мин"


def safe_name(name: str) -> str:
    name = name.replace("/", "__").replace("\\", "__")
    for ch in '<>:"|?*':
        name = name.replace(ch, "_")
    return name.strip(" .")[:120] or "model"


def is_model_file(name: str) -> bool:
    lower = name.lower()
    if lower.startswith(".") or lower.endswith(SKIP_SUFFIXES):
        return False
    return lower.endswith(KEEP_SUFFIXES)


def ssl_context() -> ssl.SSLContext:
    bundle = os.environ.get("OVS_CA_BUNDLE")
    if bundle and Path(bundle).exists():
        try:
            return ssl.create_default_context(cafile=bundle)
        except Exception:
            pass
    return ssl.create_default_context()


def build_opener(proxy: str = "") -> urllib.request.OpenerDirector:
    handlers = [urllib.request.HTTPSHandler(context=ssl_context())]
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)


def api_json(opener, url: str, token: str) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with opener.open(req, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def file_size(sibling: dict) -> int:
    lfs = sibling.get("lfs") or {}
    return int(lfs.get("size") or sibling.get("size") or 0)


def is_stopped(stop_file: Path) -> bool:
    return bool(str(stop_file)) and str(stop_file) not in (".", "") and stop_file.exists()


def download_file(
    opener,
    url: str,
    target: Path,
    expected: int,
    token: str,
    progress_cb,
    stop_file: Path,
) -> None:
    part = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, MAX_RETRIES + 1):
        if is_stopped(stop_file):
            raise RuntimeError("Загрузка отменена.")
        existing = part.stat().st_size if part.exists() else 0
        if expected and existing > expected:
            part.unlink(missing_ok=True)
            existing = 0
        if expected and existing == expected:
            os.replace(part, target)
            return
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with opener.open(request, timeout=120) as response:
                status = getattr(response, "status", 200)
                mode = "ab" if existing and status == 206 else "wb"
                if mode == "wb":
                    existing = 0
                received = existing
                with open(part, mode) as handle:
                    while True:
                        if is_stopped(stop_file):
                            raise RuntimeError("Загрузка отменена.")
                        chunk = response.read(CHUNK)
                        if not chunk:
                            break
                        handle.write(chunk)
                        received += len(chunk)
                        progress_cb(len(chunk), received, expected)
                if expected and received < expected:
                    raise IOError(f"получено {received} из {expected} байт")
            if expected and part.stat().st_size != expected:
                raise IOError("размер файла не совпал")
            os.replace(part, target)
            return
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise RuntimeError(
                    "Hugging Face отклонил доступ (401/403). Проверьте HF-токен в настройках."
                ) from exc
            if exc.code == 416:
                part.unlink(missing_ok=True)
                continue
            if exc.code == 404:
                raise RuntimeError("Файл не найден на Hugging Face (404).") from exc
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"HTTP {exc.code} при скачивании файла.") from exc
            time.sleep(1.5 * attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError, IOError) as exc:
            if is_stopped(stop_file):
                raise RuntimeError("Загрузка отменена.") from exc
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Сеть недоступна: {exc}") from exc
            log(f"Повтор загрузки ({attempt}/{MAX_RETRIES}): {exc}")
            time.sleep(1.5 * attempt)


def main() -> None:
    args_path = Path(sys.argv[1])
    args = json.loads(args_path.read_text(encoding="utf-8"))
    repo = (args.get("repo") or "").strip().strip("/")
    token = (args.get("token") or "").strip()
    proxy = (args.get("proxy") or "").strip()
    revision = args.get("revision") or "main"
    stop_file = Path(args.get("_stop_file") or "")
    models_root = Path(os.environ.get("OVS_MODELS") or (Path.cwd() / "models"))
    dest = models_root / safe_name(args.get("dest") or repo)
    selected = args.get("files") or None

    if not repo or repo.count("/") != 1:
        raise SystemExit("Некорректный идентификатор модели.")
    opener = build_opener(proxy)
    emit("detail", detail="Получение списка файлов…")
    info = api_json(opener, f"{HF_API}/models/{repo}?blobs=true", token)
    siblings = info.get("siblings") or []
    if not siblings:
        raise SystemExit("В репозитории нет файлов.")

    if selected:
        wanted = set(selected)
        files = [
            {"name": s.get("rfilename"), "size": file_size(s)}
            for s in siblings
            if s.get("rfilename") in wanted
        ]
    else:
        files = [
            {"name": s.get("rfilename"), "size": file_size(s)}
            for s in siblings
            if is_model_file(s.get("rfilename") or "")
        ]
    files = [f for f in files if f["name"]]
    if not files:
        raise SystemExit("Не найдено файлов модели для скачивания.")
    total = sum(f["size"] for f in files)

    if dest.exists() and not (dest / ".ovstudio.json").exists():
        # Unrelated folder with the same name.
        if any(dest.iterdir()):
            raise SystemExit(f"Папка {dest.name} уже существует и не является загрузкой OpenVINO Studio.")
    dest.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(dest).free
    if total and free < total * 1.05:
        raise SystemExit(
            f"Недостаточно места: нужно {human_size(total)}, свободно {human_size(free)}."
        )

    meta_path = dest / ".ovstudio.json"
    existing_meta = {}
    if meta_path.exists():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            existing_meta = {}
        if existing_meta.get("repo_id") and existing_meta.get("repo_id") != repo:
            raise SystemExit("Папка с таким именем уже занята другой моделью.")
    meta = {
        "repo_id": repo,
        "source": "huggingface",
        "pipeline_tag": info.get("pipeline_tag") or existing_meta.get("pipeline_tag") or "",
        "sha": info.get("sha") or "",
        "display_name": repo.split("/")[-1],
        "incomplete": True,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files_total": len(files),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    emit("detail", detail=f"Скачивание {repo}")
    log(f"Репозиторий: {repo}")
    log(f"Файлов: {len(files)}, объём: {human_size(total)}")
    log(f"Папка: {dest}")

    started = time.time()
    done_bytes = 0
    last_emit = 0.0

    def make_progress(base: int):
        def progress_cb(delta: int, received: int, expected: int) -> None:
            nonlocal done_bytes, last_emit
            done_bytes = base + received
            now = time.time()
            if now - last_emit < 0.45 and (not total or done_bytes < total):
                return
            last_emit = now
            elapsed = max(0.001, now - started)
            speed = done_bytes / elapsed
            ratio = (done_bytes / total) if total else 0.0
            eta = ((total - done_bytes) / speed) if speed > 0 and total else 0
            emit(
                "progress",
                value=max(0.0, min(1.0, ratio)),
                detail=(
                    f"{human_size(done_bytes)} / {human_size(total)} · "
                    f"{human_size(speed)}/с · осталось {human_eta(eta)}"
                ),
            )
        return progress_cb

    try:
        for index, item in enumerate(files, 1):
            name = item["name"]
            target = dest / name
            expected = item["size"]
            if target.exists() and (not expected or target.stat().st_size == expected):
                done_bytes += expected
                continue
            emit(
                "detail",
                detail=f"Файл {index}/{len(files)}: {name}",
            )
            log(f"[{index}/{len(files)}] {name} ({human_size(expected)})")
            url = f"{HF_SITE}/{repo}/resolve/{urllib.parse.quote(revision)}/{urllib.parse.quote(name, safe='/')}"
            download_file(opener, url, target, expected, token, make_progress(done_bytes), stop_file)
        # Ensure tokens/IR arrived.
        names = {p.name.lower() for p in dest.iterdir() if p.is_file()}
        if not any(n.endswith(".xml") for n in names):
            log("Внимание: в репозитории нет .xml — это не готовый OpenVINO IR.")
        size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
        meta.update(
            {
                "incomplete": False,
                "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "size": size,
                "files": [f["name"] for f in files],
                "task": info.get("pipeline_tag") or "",
            }
        )
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        emit(
            "result",
            data={
                "path": str(dest),
                "name": dest.name,
                "size": size,
                "size_label": human_size(size),
                "repo": repo,
                "files": len(files),
            },
        )
        emit("progress", value=1.0, detail="Готово")
        log(f"Готово: {dest} ({human_size(size)})")
    except Exception:
        # Leave metadata marked incomplete so the download can be resumed later.
        try:
            meta["incomplete"] = True
            meta["error"] = "download interrupted"
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        emit("error", message=str(exc))
        raise
