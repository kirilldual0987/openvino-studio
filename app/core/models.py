"""Local model library scanning and metadata."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from . import config
from .util import atomic_write_json, dir_size, human_size, is_relative_to, log, read_json

META_FILE = ".ovstudio.json"

LLM_TAGS = {"text-generation", "image-text-to-text", "text2text-generation"}
IMAGE_TAGS = {"image-classification", "object-detection", "image-segmentation"}
AUDIO_TAGS = {"automatic-speech-recognition", "text-to-speech", "audio-classification"}
EMBED_TAGS = {"feature-extraction", "sentence-similarity", "text-ranking"}


def meta_path(folder: Path) -> Path:
    return folder / META_FILE


def read_meta(folder: Path) -> dict:
    data = read_json(meta_path(folder), {})
    return data if isinstance(data, dict) else {}


def write_meta(folder: Path, patch: dict) -> dict:
    data = read_meta(folder)
    data.update(patch)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        atomic_write_json(meta_path(folder), data)
    except Exception as exc:
        log(f"cannot write metadata {folder}: {exc}")
    return data


def _read_config(folder: Path) -> dict:
    for name in ("config.json", "openvino_config.json"):
        data = read_json(folder / name, None)
        if isinstance(data, dict):
            return data
    return {}


def _has_tokenizer(folder: Path) -> bool:
    names = {p.name.lower() for p in folder.iterdir() if p.is_file()}
    return bool(
        {"tokenizer.json", "tokenizer_config.json", "openvino_tokenizer.xml", "vocab.json", "tokenizer.model"}
        & names
    )


def detect_kind(folder: Path, meta: dict | None = None) -> tuple[str, dict]:
    """Return (kind, details) where kind is llm/vlm/image/audio/embedding/unknown."""
    meta = meta if meta is not None else read_meta(folder)
    config_data = _read_config(folder)
    tag = (meta.get("pipeline_tag") or meta.get("task") or "").lower()
    architectures = [str(a).lower() for a in (config_data.get("architectures") or [])]
    model_type = str(config_data.get("model_type") or "").lower()
    names = {p.name.lower() for p in folder.iterdir() if p.is_file()}
    is_text_task = tag.startswith(("text-generation", "text2text-generation"))
    has_generation = "generation_config.json" in names or is_text_task or tag in LLM_TAGS
    has_tokenizer = _has_tokenizer(folder)
    has_ir = any(n.endswith(".xml") and "tokenizer" not in n for n in names)
    id2label = bool(config_data.get("id2label"))
    has_preprocessor = "preprocessor_config.json" in names
    has_labels = bool(config_data.get("labels"))
    is_causal = any(
        marker in architecture
        for architecture in architectures
        for marker in ("forcausallm", "lmheadmodel", "causallm", "forconditionalgeneration", "gpt2lmhead")
    ) or model_type in {
        "qwen2",
        "qwen3",
        "llama",
        "phi3",
        "phi4",
        "mistral",
        "gemma",
        "gemma2",
        "gemma3",
        "deepseek_v3",
        "gpt2",
        "gpt_neo",
        "gptj",
        "gpt_bigcode",
        "bloom",
        "opt",
        "falcon",
        "mpt",
        "starcoder2",
        "cohere",
        "internlm2",
        "glm",
        "yi",
    }
    is_vlm = tag == "image-text-to-text" or "vision" in " ".join(architectures) or model_type in {
        "qwen2_vl",
        "qwen2_5_vl",
        "gemma3",
        "llava",
        "internvl_chat",
    }
    is_whisper = tag == "automatic-speech-recognition" or "whisper" in model_type or any(
        "whisper" in a for a in architectures
    )

    details = {
        "architectures": architectures[:3],
        "model_type": model_type,
        "has_tokenizer": has_tokenizer,
        "has_ir": has_ir,
        "id2label": id2label,
        "pipeline_tag": tag,
    }
    if not has_ir:
        details["kind"] = "unknown"
        return "unknown", details
    if is_whisper:
        return "audio", details
    if tag in EMBED_TAGS or model_type in {"bert", "xlm-roberta", "qwen3", "qwen2"} and "embedding" in (
        folder.name.lower()
    ):
        if "embedding" in folder.name.lower() or tag in EMBED_TAGS:
            return "embedding", details
    if tag in LLM_TAGS or is_text_task or (has_generation and has_tokenizer and is_causal):
        if is_vlm:
            return "vlm", details
        return "llm", details
    if tag in IMAGE_TAGS or id2label or has_preprocessor or has_labels:
        model_type_lower = str(config_data.get("model_type") or "").lower()
        if (
            tag == "object-detection"
            or "yolo" in folder.name.lower()
            or "yolo" in model_type_lower
            or "det" in folder.name.lower()
            or "iou_threshold" in config_data
            or "detr" in model_type_lower
        ):
            return "detection", details
        return "image", details
    return "unknown", details


def find_ir(folder: Path) -> Path | None:
    preferred = ["openvino_model.xml", "openvino_language_model.xml", "openvino_vision_model.xml"]
    by_name = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
    for name in preferred:
        if name in by_name:
            return by_name[name]
    for name, path in sorted(by_name.items()):
        if name.endswith(".xml") and "tokenizer" not in name and "detokenizer" not in name:
            return path
    return None


def list_models() -> list[dict]:
    root = config.models_dir()
    if not root.exists():
        return []
    items: list[dict] = []
    for folder in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        try:
            meta = read_meta(folder)
            kind, details = detect_kind(folder, meta)
            size = dir_size(folder)
            ir = find_ir(folder)
            if not ir and kind == "unknown":
                # Incomplete or non-OpenVINO folder: still show it so users can remove it.
                pass
            items.append(
                {
                    "id": folder.name,
                    "name": meta.get("display_name") or folder.name,
                    "repo": meta.get("repo_id") or meta.get("source_repo") or "",
                    "kind": kind,
                    "kind_label": {
                        "llm": "LLM",
                        "vlm": "VLM",
                        "image": "Изображения",
                        "detection": "Детекция",
                        "audio": "Аудио",
                        "embedding": "Эмбеддинги",
                        "unknown": "Другое",
                    }[kind],
                    "chat_ready": kind == "llm" and details.get("has_tokenizer", False),
                    "vlm_ready": kind == "vlm" and details.get("has_tokenizer", False),
                    "task": meta.get("task") or meta.get("pipeline_tag") or details.get("pipeline_tag") or "",
                    "size": size,
                    "size_label": human_size(size),
                    "files": sum(1 for p in folder.iterdir() if p.is_file()),
                    "has_ir": bool(ir),
                    "ir": ir.name if ir else "",
                    "incomplete": bool(meta.get("incomplete")),
                    "downloaded_at": meta.get("downloaded_at") or meta.get("converted_at") or "",
                    "updated_at": meta.get("updated_at") or "",
                    "source": meta.get("source") or ("converted" if meta.get("source_repo") else "local"),
                    "weight_format": meta.get("weight_format") or "",
                    "mtime": folder.stat().st_mtime,
                    "details": details,
                }
            )
        except Exception as exc:
            log(f"scan error {folder.name}: {exc}")
    items.sort(key=lambda item: item.get("mtime", 0), reverse=True)
    return items


def library_summary() -> dict:
    models = list_models()
    total = sum(m["size"] for m in models)
    root = config.models_dir()
    return {
        "count": len(models),
        "total_size": total,
        "total_size_label": human_size(total),
        "path": str(root),
        "models": models,
    }


def delete_model(model_id: str) -> None:
    root = config.models_dir().resolve()
    target = (root / model_id).resolve()
    if target == root or not is_relative_to(target, root) or target.name != model_id:
        raise ValueError("Некорректный путь модели.")
    if not target.is_dir():
        raise FileNotFoundError("Модель не найдена.")
    shutil.rmtree(target, onerror=_force_remove)


def _force_remove(func, path, _exc_info):
    try:
        os.chmod(path, 0o700)
        func(path)
    except Exception:
        pass


def benchmark_history_path() -> Path:
    return config.RUNTIME_DIR / "benchmarks.json"


def add_benchmark_result(result: dict) -> None:
    history = read_json(benchmark_history_path(), [])
    if not isinstance(history, list):
        history = []
    history.insert(0, result)
    atomic_write_json(benchmark_history_path(), history[:80])


def benchmark_history() -> list:
    data = read_json(benchmark_history_path(), [])
    return data if isinstance(data, list) else []
