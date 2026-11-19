"""Benchmark an OpenVINO model (classic IR or generative LLM)."""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import traceback
from pathlib import Path

DTYPES = {
    "f32": "float32",
    "f16": "float16",
    "f64": "float64",
    "i64": "int64",
    "i32": "int32",
    "i16": "int16",
    "i8": "int8",
    "u8": "uint8",
    "u16": "uint16",
    "u32": "uint32",
    "boolean": "bool",
    "float32": "float32",
    "float16": "float16",
    "float64": "float64",
    "int64": "int64",
    "int32": "int32",
    "int16": "int16",
    "int8": "int8",
    "uint8": "uint8",
    "uint16": "uint16",
    "uint32": "uint32",
    "boolean": "bool",
}


def emit(event: str, **data) -> None:
    print("@@JSON@@" + json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def log(message: str) -> None:
    emit("log", message=str(message))


def find_ir(folder: Path) -> Path | None:
    for name in ("openvino_model.xml", "openvino_language_model.xml"):
        path = folder / name
        if path.exists():
            return path
    for path in sorted(folder.glob("*.xml")):
        lower = path.name.lower()
        if "tokenizer" not in lower and "detokenizer" not in lower:
            return path
    return None


def is_llm(folder: Path) -> bool:
    if (folder / "openvino_language_model.xml").exists():
        return True
    tokenizer = any(
        (folder / name).exists()
        for name in ("tokenizer.json", "tokenizer_config.json", "openvino_tokenizer.xml")
    )
    generation = (folder / "generation_config.json").exists()
    return tokenizer and generation


def build_inputs(core, model):
    import numpy as np

    feed = {}
    shapes = {}
    for model_input in model.inputs:
        partial = model_input.get_partial_shape()
        dims = []
        rank = len(partial)
        for index, dim in enumerate(partial):
            if dim.is_dynamic:
                if rank == 4 and index == 1:
                    dims.append(3)
                elif rank == 4 and index in (2, 3):
                    dims.append(224)
                else:
                    dims.append(1)
            else:
                dims.append(int(dim.get_length()))
        type_name = str(model_input.get_element_type().get_type_name())
        numpy_type = getattr(np, DTYPES.get(type_name, "float32"))
        if np.issubdtype(numpy_type, np.floating):
            array = np.random.rand(*dims).astype(numpy_type)
        else:
            array = np.zeros(dims, dtype=numpy_type)
        feed[model_input.get_any_name()] = array
        shapes[model_input.get_any_name()] = {
            "shape": dims,
            "type": type_name,
        }
    return feed, shapes


def run_classic(args: dict) -> None:
    import openvino as ov

    folder = Path(args["model"])
    device = args.get("device") or "CPU"
    iterations = max(1, int(args.get("iterations", 10)))
    warmup = max(0, int(args.get("warmup", 2)))
    ir = find_ir(folder)
    if not ir:
        emit("error", message="Не найден .xml файл модели.")
        return
    emit("detail", detail="Чтение модели…")
    core = ov.Core()
    model = core.read_model(str(ir))
    feed, shapes = build_inputs(core, model)
    emit("progress", value=0.15, detail="Компиляция модели…")
    compile_started = time.time()
    threads = int(args.get("num_threads") or 0)
    properties = {}
    cache_dir = os.environ.get("OV_CACHE_DIR")
    if cache_dir:
        properties["CACHE_DIR"] = cache_dir
    if threads and str(device).upper().startswith("CPU"):
        properties["INFERENCE_NUM_THREADS"] = threads
    compiled = core.compile_model(model, device, properties)
    compile_ms = (time.time() - compile_started) * 1000.0
    log(f"Модель скомпилирована за {compile_ms:.0f} мс на {device}")
    for _ in range(warmup):
        compiled(feed)
    latencies = []
    for index in range(iterations):
        started = time.perf_counter()
        compiled(feed)
        latencies.append((time.perf_counter() - started) * 1000.0)
        emit(
            "progress",
            value=0.2 + 0.75 * (index + 1) / iterations,
            detail=f"Итерация {index + 1} из {iterations}",
        )
    latencies_sorted = sorted(latencies)
    mean = statistics.fmean(latencies)
    result = {
        "mode": "classic",
        "device": device,
        "model": folder.name,
        "ir": ir.name,
        "iterations": iterations,
        "warmup": warmup,
        "latency_mean_ms": round(mean, 2),
        "latency_min_ms": round(min(latencies), 2),
        "latency_max_ms": round(max(latencies), 2),
        "latency_p50_ms": round(statistics.median(latencies), 2),
        "latency_p90_ms": round(latencies_sorted[min(len(latencies_sorted) - 1, int(len(latencies_sorted) * 0.9))], 2),
        "throughput_fps": round(1000.0 / mean, 2) if mean else 0,
        "compile_ms": round(compile_ms, 1),
        "inputs": shapes,
        "size": sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    emit("result", data=result)
    log(
        f"Средняя задержка: {result['latency_mean_ms']} мс · "
        f"{result['throughput_fps']} кадров/с"
    )


def run_llm(args: dict) -> None:
    try:
        import openvino_genai as ov_genai
    except Exception:
        emit(
            "error",
            message=(
                "Для бенчмарка LLM нужен OpenVINO GenAI. Установите его в «Инструменты» → «Компоненты»."
            ),
        )
        return
    folder = Path(args["model"])
    device = args.get("device") or "CPU"
    iterations = max(1, int(args.get("iterations", 3)))
    warmup = max(0, int(args.get("warmup", 1)))
    max_tokens = max(8, int(args.get("max_new_tokens", 64)))
    prompt = args.get("prompt") or "The capital of France is"
    emit("detail", detail="Загрузка LLM…")
    load_started = time.time()
    threads = int(args.get("num_threads") or 0)
    properties = {}
    cache_dir = os.environ.get("OV_CACHE_DIR")
    if cache_dir:
        properties["CACHE_DIR"] = cache_dir
    if threads and str(device).upper().startswith("CPU"):
        properties["INFERENCE_NUM_THREADS"] = threads
    pipe = ov_genai.LLMPipeline(str(folder), device, properties)
    load_ms = (time.time() - load_started) * 1000.0
    config = ov_genai.GenerationConfig()
    config.max_new_tokens = max_tokens
    config.do_sample = False
    config.apply_chat_template = False
    emit("progress", value=0.2, detail="Прогрев…")
    for _ in range(warmup):
        pipe.generate([prompt], config)
    total_tokens = 0
    durations = []
    ttfts = []
    tps_values = []
    for index in range(iterations):
        emit(
            "progress",
            value=0.25 + 0.7 * (index + 1) / iterations,
            detail=f"Генерация {index + 1} из {iterations}",
        )
        started = time.time()
        result = pipe.generate([prompt], config)
        durations.append((time.time() - started) * 1000.0)
        try:
            perf = result.perf_metrics
            total_tokens += int(perf.get_num_generated_tokens())
            ttfts.append(float(perf.get_ttft().mean))
            tps_values.append(float(perf.get_throughput().mean))
        except Exception:
            total_tokens += max_tokens
    mean = statistics.fmean(durations)
    avg_tps = statistics.fmean(tps_values) if tps_values else (total_tokens / (sum(durations) / 1000.0))
    output = {
        "mode": "llm",
        "device": device,
        "model": folder.name,
        "iterations": iterations,
        "warmup": warmup,
        "max_new_tokens": max_tokens,
        "prompt": prompt,
        "latency_mean_ms": round(mean, 1),
        "latency_min_ms": round(min(durations), 1),
        "latency_max_ms": round(max(durations), 1),
        "latency_p50_ms": round(statistics.median(durations), 1),
        "latency_p90_ms": round(sorted(durations)[min(len(durations) - 1, int(len(durations) * 0.9))], 1),
        "throughput_fps": round(avg_tps, 2),
        "throughput_tps": round(avg_tps, 2),
        "ttft_ms": round(statistics.fmean(ttfts), 1) if ttfts else None,
        "load_ms": round(load_ms, 1),
        "tokens": total_tokens,
        "size": sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    emit("result", data=output)
    log(f"Скорость: {output['throughput_tps']} токенов/с · TTFT {output['ttft_ms']} мс")


def main() -> None:
    args = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    folder = Path(args["model"])
    mode = args.get("mode") or "auto"
    if mode == "auto":
        mode = "llm" if is_llm(folder) else "classic"
    if mode == "llm":
        run_llm(args)
    else:
        run_classic(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit("error", message=f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        sys.exit(1)
