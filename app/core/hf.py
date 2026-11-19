"""Hugging Face Hub access without third-party dependencies."""
from __future__ import annotations

import json
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config
from .util import log

HF_API = "https://huggingface.co/api"
HF_SITE = "https://huggingface.co"
USER_AGENT = "OpenVINO-Studio/1.0 (+local desktop app)"

_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()
CACHE_TTL = 300


class HFError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def _ca_bundle() -> str | None:
    path = Path(__file__).resolve().parents[2] / "app" / "assets" / "cacert.pem"
    return str(path) if path.exists() else None


def _open(request: urllib.request.Request, timeout: int = 25):
    handlers = []
    proxy = ""
    try:
        from . import config as _cfg

        proxy = _cfg.load_settings().get("proxy") or ""
    except Exception:
        proxy = ""
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            bundle = _ca_bundle()
            if bundle:
                context = ssl.create_default_context(cafile=bundle)
                opener = urllib.request.build_opener(
                    *handlers, urllib.request.HTTPSHandler(context=context)
                )
                return opener.open(request, timeout=timeout)
        raise


def api_get(path: str, params: dict | None = None, timeout: int = 25) -> object:
    settings = config.load_settings()
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v not in (None, "")})
    url = f"{HF_API}{path}" + (f"?{query}" if query else "")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    token = (settings.get("hf_token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with _open(request, timeout=timeout) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HFError("Доступ к модели закрыт. Укажите HF-токен в настройках.", exc.code) from exc
        if exc.code == 404:
            raise HFError("Модель не найдена на Hugging Face.", 404) from exc
        if exc.code == 429:
            raise HFError("Слишком много запросов к Hugging Face. Попробуйте позже.", 429) from exc
        raise HFError(f"Hugging Face вернул ошибку {exc.code}.", exc.code) from exc
    except urllib.error.URLError as exc:
        raise HFError(f"Нет связи с Hugging Face: {exc.reason}", 0) from exc
    except TimeoutError as exc:
        raise HFError("Hugging Face не ответил вовремя.", 0) from exc


def _cached(key: str):
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
    return None


def _store(key: str, value) -> None:
    with _cache_lock:
        _cache[key] = (time.time(), value)
        if len(_cache) > 200:
            oldest = sorted(_cache.items(), key=lambda kv: kv[1][0])[:50]
            for k, _ in oldest:
                _cache.pop(k, None)


def normalize_model(item: dict) -> dict:
    repo = item.get("id") or item.get("modelId") or ""
    tags = item.get("tags") or []
    return {
        "repo": repo,
        "author": repo.split("/")[0] if "/" in repo else "",
        "name": repo.split("/")[-1],
        "downloads": item.get("downloads") or 0,
        "likes": item.get("likes") or 0,
        "pipeline_tag": item.get("pipeline_tag") or "",
        "tags": [t for t in tags if not t.startswith(("base_model:", "dataset:", "arxiv:", "license:"))][:8],
        "last_modified": item.get("lastModified") or "",
        "gated": bool(item.get("gated")),
        "private": bool(item.get("private")),
    }


def search(
    query: str = "",
    task: str = "",
    author: str = "",
    sort: str = "downloads",
    limit: int = 30,
) -> list[dict]:
    params: dict[str, str | int] = {
        "filter": "openvino",
        "sort": sort if sort in ("downloads", "likes", "lastModified") else "downloads",
        "direction": -1,
        "limit": max(1, min(60, int(limit))),
    }
    if query:
        params["search"] = query
    if task:
        params["pipeline_tag"] = task
    if author:
        params["author"] = author
    key = "search:" + json.dumps(params, sort_keys=True, ensure_ascii=False)
    cached = _cached(key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    items = api_get("/models", params)
    if not isinstance(items, list):
        raise HFError("Неожиданный ответ Hugging Face.")
    result = [normalize_model(item) for item in items if item.get("id")]
    _store(key, result)
    return result


def _file_size(sibling: dict) -> int:
    lfs = sibling.get("lfs") or {}
    return int(lfs.get("size") or sibling.get("size") or 0)


def is_weight_file(name: str) -> bool:
    lower = name.lower()
    if lower.startswith(".") or lower.endswith((".md", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp4", ".pdf")):
        return False
    if lower.endswith((".xml", ".bin", ".model", ".json", ".txt", ".tiktoken", ".jinja", ".py", ".yaml", ".yml")):
        return True
    return False


def model_detail(repo: str) -> dict:
    repo = (repo or "").strip().strip("/")
    if not repo or repo.count("/") > 1 or ".." in repo:
        raise HFError("Некорректный идентификатор модели.", 400)
    key = "detail:" + repo
    cached = _cached(key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    data = api_get(f"/models/{repo}", {"blobs": "true"})
    if not isinstance(data, dict):
        raise HFError("Неожиданный ответ Hugging Face.")
    files = []
    total = 0
    for sibling in data.get("siblings") or []:
        name = sibling.get("rfilename") or ""
        if not name:
            continue
        size = _file_size(sibling)
        files.append({"name": name, "size": size})
        total += size
    files.sort(key=lambda item: item["name"])
    has_ir = any(f["name"].lower().endswith(".xml") and "tokenizer" not in f["name"].lower() for f in files)
    detail = normalize_model(data)
    detail.update(
        {
            "files": files,
            "total_size": total,
            "has_ir": has_ir,
            "downloadable_size": sum(
                f["size"] for f in files if is_weight_file(f["name"])
            ),
            "license": ((data.get("cardData") or {}).get("license") or ""),
            "readme": fetch_readme(repo),
        }
    )
    _store(key, detail)
    return detail


def fetch_readme(repo: str, limit: int = 40000) -> str:
    url = f"{HF_SITE}/{repo}/resolve/main/README.md"
    settings = config.load_settings()
    headers = {"User-Agent": USER_AGENT}
    token = (settings.get("hf_token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with _open(request, timeout=20) as response:
            raw = response.read(limit + 512)
        text = raw.decode("utf-8", "replace")
        if len(text) > limit:
            text = text[:limit] + "\n\n…"
        return text
    except Exception as exc:
        log(f"README fetch failed for {repo}: {exc}", 30)
        return ""


def resolve_url(repo: str, filename: str, revision: str = "main") -> str:
    quoted = urllib.parse.quote(filename, safe="/")
    return f"{HF_SITE}/{repo}/resolve/{urllib.parse.quote(revision, safe='')}/{quoted}"
