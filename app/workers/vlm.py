"""Streaming vision-language chat worker built on OpenVINO GenAI."""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path


def emit(event: str, **data) -> None:
    print("@@JSON@@" + json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def log(message: str) -> None:
    emit("log", message=str(message))


def main() -> None:
    args = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    raw_stop = str(args.get("_stop_file") or "")
    stop_file = Path(raw_stop) if raw_stop else None
    model = args["model"]
    device = args.get("device") or "CPU"
    image_path = args["image"]
    prompt = args.get("prompt") or "Опиши изображение подробно."
    system = (args.get("system") or "").strip()
    params = args.get("params") or {}

    emit("status", detail="Загрузка OpenVINO GenAI…")
    try:
        import openvino_genai as ov_genai
        from openvino import Tensor
        import numpy as np
        from PIL import Image
    except Exception as exc:
        emit(
            "error",
            message=(
                "Не установлены компоненты для VLM. Нужны OpenVINO Runtime, GenAI и Pillow. "
                "Установите их в «Инструменты» → «Компоненты». " + str(exc)
            ),
        )
        return

    try:
        picture = Image.open(image_path).convert("RGB")
        image_tensor = Tensor(np.array(picture))
    except Exception as exc:
        emit("error", message=f"Не удалось прочитать изображение: {exc}")
        return

    emit("status", detail="Загрузка модели…")
    load_started = time.time()
    properties = {}
    cache_dir = os.environ.get("OV_CACHE_DIR")
    if cache_dir:
        properties["CACHE_DIR"] = cache_dir
    threads = int(args.get("num_threads") or 0)
    if threads and str(device).upper().startswith("CPU"):
        properties["INFERENCE_NUM_THREADS"] = threads
    try:
        pipe = ov_genai.VLMPipeline(model, device, **properties)
    except Exception as exc:
        emit("error", message=f"Не удалось загрузить VLM на {device}: {exc}")
        log(traceback.format_exc())
        return
    load_ms = (time.time() - load_started) * 1000.0
    emit("status", detail="Модель загружена, анализируем изображение…", load_ms=round(load_ms, 1))

    config = ov_genai.GenerationConfig()
    config.max_new_tokens = int(params.get("max_new_tokens", 512))
    temperature = float(params.get("temperature", 0.4))
    config.do_sample = bool(params.get("do_sample", temperature > 0.01))
    config.temperature = temperature
    config.top_p = float(params.get("top_p", 0.9))
    config.top_k = int(params.get("top_k", 40))
    config.repetition_penalty = float(params.get("repetition_penalty", 1.05))

    history = ov_genai.ChatHistory()
    if system:
        history.append({"role": "system", "content": system})
    history.append({"role": "user", "content": prompt})

    class Counter:
        count = 0

    counter = Counter()

    def streamer(token):
        if stop_file is not None and stop_file.exists():
            return True
        text = token if isinstance(token, str) else str(token)
        counter.count += 1
        emit("token", text=text)
        return False

    started = time.time()
    try:
        result = pipe.generate(history, images=[image_tensor], generation_config=config, streamer=streamer)
    except Exception as exc:
        emit("error", message=f"Ошибка VLM: {exc}")
        log(traceback.format_exc())
        return
    elapsed = time.time() - started
    metrics = {}
    try:
        perf = result.perf_metrics
        metrics = {
            "tokens": int(perf.get_num_generated_tokens()),
            "prompt_tokens": int(perf.get_num_input_tokens()),
            "ttft_ms": round(float(perf.get_ttft().mean), 1),
            "tpot_ms": round(float(perf.get_tpot().mean), 2),
            "throughput": round(float(perf.get_throughput().mean), 2),
            "load_ms": round(load_ms, 1),
            "elapsed": round(elapsed, 2),
        }
    except Exception:
        metrics = {"tokens": counter.count, "elapsed": round(elapsed, 2), "load_ms": round(load_ms, 1)}
    emit("done", metrics=metrics)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit("error", message=str(exc))
        traceback.print_exc()
        sys.exit(1)
