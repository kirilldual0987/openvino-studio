"""Image classification / YOLO-style detection with a plain OpenVINO IR."""
from __future__ import annotations

import base64
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PALETTE = [
    (63, 81, 181),
    (0, 121, 107),
    (194, 24, 91),
    (245, 124, 0),
    (25, 118, 210),
    (123, 31, 162),
    (46, 125, 50),
    (230, 81, 0),
    (2, 119, 189),
    (156, 39, 176),
]


def emit(event: str, **data) -> None:
    print("@@JSON@@" + json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def log(message: str) -> None:
    emit("log", message=str(message))


def find_ir(folder: Path) -> Path | None:
    for path in sorted(folder.glob("*.xml")):
        lower = path.name.lower()
        if "tokenizer" not in lower and "detokenizer" not in lower:
            if path.name == "openvino_model.xml":
                return path
    for path in sorted(folder.glob("*.xml")):
        lower = path.name.lower()
        if "tokenizer" not in lower and "detokenizer" not in lower:
            return path
    return None


def load_config(folder: Path) -> dict:
    for name in ("config.json", "openvino_config.json"):
        path = folder / name
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def parse_floats(value) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [float(v) for v in value]
    text = str(value).replace(",", " ").split()
    result = []
    for part in text:
        try:
            result.append(float(part))
        except ValueError:
            pass
    return result


def parse_labels(config: dict) -> list[str]:
    labels = config.get("labels")
    if isinstance(labels, list):
        return [str(x) for x in labels]
    if isinstance(labels, str) and labels.strip():
        return labels.split()
    id2label = config.get("id2label")
    if isinstance(id2label, dict):
        pairs = sorted(((int(k), v) for k, v in id2label.items()), key=lambda kv: kv[0])
        return [str(v) for _, v in pairs]
    return []


def softmax(values: np.ndarray) -> np.ndarray:
    values = values.astype(np.float64)
    values = values - np.max(values)
    exp = np.exp(values)
    return exp / max(1e-12, float(np.sum(exp)))


def letterbox(image: Image.Image, size: tuple[int, int], pad: int = 114) -> tuple[Image.Image, float, int, int]:
    target_w, target_h = size
    scale = min(target_w / image.width, target_h / image.height)
    new_w = max(1, int(round(image.width * scale)))
    new_h = max(1, int(round(image.height * scale)))
    resized = image.resize((new_w, new_h), Image.BILINEAR)
    canvas = Image.new("RGB", (target_w, target_h), (pad, pad, pad))
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))
    return canvas, scale, offset_x, offset_y


def preprocess(image: Image.Image, config: dict, size: tuple[int, int], letterbox_mode: bool):
    mean = parse_floats(config.get("mean_values"))
    scale = parse_floats(config.get("scale_values"))
    reverse = str(config.get("reverse_input_channels", "")).lower() in ("1", "true", "yes")
    pad = int(parse_floats(config.get("pad_value"))[0]) if parse_floats(config.get("pad_value")) else 114
    if letterbox_mode:
        canvas, ratio, dx, dy = letterbox(image, size, pad)
        image = canvas
    else:
        ratio, dx, dy = 0.0, 0, 0
        image = image.resize(size, Image.BILINEAR)
    array = np.asarray(image).astype(np.float32)
    if reverse:
        array = array[:, :, ::-1]
    if scale:
        array = array - np.array(mean, dtype=np.float32) if mean else array
        array = array / np.array(scale, dtype=np.float32)
    else:
        array = array / 255.0
    array = np.transpose(array, (2, 0, 1))[None, ...]
    return np.ascontiguousarray(array, dtype=np.float32), ratio, dx, dy


def nms(boxes: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        index = int(order[0])
        keep.append(index)
        if order.size == 1:
            break
        xx1 = np.maximum(boxes[index, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[index, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[index, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[index, 3], boxes[order[1:], 3])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        area_a = (boxes[index, 2] - boxes[index, 0]) * (boxes[index, 3] - boxes[index, 1])
        area_b = (boxes[order[1:], 2] - boxes[order[1:], 0]) * (boxes[order[1:], 3] - boxes[order[1:], 1])
        iou = inter / np.maximum(1e-9, area_a + area_b - inter)
        order = order[1:][iou <= threshold]
    return keep


def decode_detection(output: np.ndarray, labels: list[str], ratio: float, dx: int, dy: int, original_size, threshold: float, iou_threshold: float):
    arr = np.asarray(output, dtype=np.float32)
    while arr.ndim > 3:
        arr = arr[0]
    if arr.ndim == 3:
        arr = arr[0]
    if arr.ndim == 2 and arr.shape[0] < arr.shape[1]:
        arr = arr.T
    if arr.ndim != 2 or arr.shape[1] < 6:
        raise ValueError("Форма выхода не похожа на детектор объектов.")
    width, height = original_size
    boxes = []
    scores = []
    classes = []
    decoded = False
    if arr.shape[1] == 6:
        sample = arr[:8]
        if np.all(sample[:, 2] >= sample[:, 0]) and np.all(sample[:, 3] >= sample[:, 1]):
            decoded = True
    for row in arr:
        if decoded:
            x1, y1, x2, y2, score, cls = row[:6]
            cls_id = int(cls)
        else:
            cx, cy, w, h = row[:4]
            probs = row[4:]
            cls_id = int(np.argmax(probs))
            score = float(probs[cls_id])
            if max(cx, cy, w, h) <= 2.0 and max(width, height) > 10:
                cx, cy, w, h = cx * 640, cy * 640, w * 640, h * 640
            x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        score = float(score)
        if score < threshold:
            continue
        if ratio:
            x1 = (float(x1) - dx) / ratio
            x2 = (float(x2) - dx) / ratio
            y1 = (float(y1) - dy) / ratio
            y2 = (float(y2) - dy) / ratio
        x1 = max(0.0, min(width, float(x1)))
        y1 = max(0.0, min(height, float(y1)))
        x2 = max(0.0, min(width, float(x2)))
        y2 = max(0.0, min(height, float(y2)))
        if x2 - x1 < 1 or y2 - y1 < 1:
            continue
        boxes.append([x1, y1, x2, y2])
        scores.append(score)
        classes.append(cls_id)
    if not boxes:
        return []
    boxes_arr = np.asarray(boxes)
    scores_arr = np.asarray(scores)
    keep = nms(boxes_arr, scores_arr, iou_threshold)
    detections = []
    for index in keep:
        cls_id = classes[index]
        label = labels[cls_id] if 0 <= cls_id < len(labels) else f"class {cls_id}"
        detections.append(
            {
                "label": label.replace("_", " "),
                "score": round(float(scores_arr[index]), 4),
                "box": [round(float(v), 1) for v in boxes_arr[index]],
            }
        )
    detections.sort(key=lambda item: item["score"], reverse=True)
    return detections[:100]


def annotate(image: Image.Image, detections: list[dict]) -> Image.Image:
    canvas = image.copy().convert("RGB")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, detection in enumerate(detections):
        x1, y1, x2, y2 = detection["box"]
        color = PALETTE[index % len(PALETTE)]
        draw.rectangle([x1, y1, x2, y2], outline=color, width=max(2, int(min(canvas.size) / 250)))
        label = f"{detection['label']} {detection['score'] * 100:.0f}%"
        try:
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = len(label) * 6, 11
        ty = max(0, y1 - th - 6)
        draw.rectangle([x1, ty, x1 + tw + 8, ty + th + 6], fill=color)
        draw.text((x1 + 4, ty + 3), label, fill=(255, 255, 255), font=font)
    return canvas


def main() -> None:
    args = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    folder = Path(args["model"])
    image_path = Path(args["image"])
    task = args.get("task") or "auto"
    top_k = max(1, min(20, int(args.get("top_k", 5))))
    threshold = float(args.get("threshold", 0.3))
    device = args.get("device") or "CPU"
    threads = int(args.get("num_threads") or 0)
    started = time.time()
    config = load_config(folder)
    labels = parse_labels(config)
    image = Image.open(image_path).convert("RGB")
    original_size = image.size
    ir = find_ir(folder)
    if not ir:
        emit("error", message="В модели нет OpenVINO IR (.xml).")
        return

    import openvino as ov

    core = ov.Core()
    model = core.read_model(str(ir))
    if not model.inputs:
        emit("error", message="У модели нет входов.")
        return
    input_node = model.inputs[0]
    shape = input_node.get_partial_shape()
    if len(shape) != 4:
        emit("error", message="Поддерживаются только модели изображений с 4D-входом.")
        return
    dims = list(shape)
    if dims[1].is_dynamic or int(dims[1].get_length()) == 3:
        layout = "NCHW"
        height = int(dims[2].get_length()) if not dims[2].is_dynamic else 224
        width = int(dims[3].get_length()) if not dims[3].is_dynamic else 224
    else:
        layout = "NHWC"
        height = int(dims[1].get_length()) if not dims[1].is_dynamic else 224
        width = int(dims[2].get_length()) if not dims[2].is_dynamic else 224
    if (layout == "NCHW" and int(dims[1].get_length() if not dims[1].is_dynamic else 3) != 3) or (
        layout == "NHWC" and int(dims[3].get_length() if not dims[3].is_dynamic else 3) != 3
    ):
        emit("error", message="Ожидается RGB-вход с 3 каналами.")
        return
    if task == "auto":
        task = "detect" if str(config.get("model_type", "")).lower().startswith(("yolo", "ssd", "detr")) or "yolo" in folder.name.lower() else "classify"
    letterbox_mode = str(config.get("resize_type", "")).lower().endswith("letterbox")
    array, ratio, dx, dy = preprocess(image, config, (width, height), letterbox_mode)
    if layout == "NHWC":
        array = np.transpose(array, (0, 2, 3, 1))
    if not input_node.get_element_type().is_real():
        array = np.clip(array, 0, 255).astype(np.uint8)
    properties = {}
    cache_dir = os.environ.get("OV_CACHE_DIR")
    if cache_dir:
        properties["CACHE_DIR"] = cache_dir
    if threads and str(device).upper().startswith("CPU"):
        properties["INFERENCE_NUM_THREADS"] = threads
    compiled = core.compile_model(model, device, properties)
    emit("detail", detail="Инференс…")
    output = compiled({input_node.get_any_name(): array})
    raw = np.asarray(output[compiled.output(0)])
    elapsed = (time.time() - started) * 1000.0

    if task == "detect":
        iou_threshold = 0.45
        try:
            iou_threshold = float(config.get("iou_threshold", 0.45))
        except (TypeError, ValueError):
            pass
        detections = decode_detection(raw, labels, ratio, dx, dy, original_size, threshold, iou_threshold)
        annotated = annotate(image, detections)
        buffer = io.BytesIO()
        annotated.save(buffer, format="JPEG", quality=90)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        emit(
            "result",
            data={
                "task": "detect",
                "detections": detections,
                "image": "data:image/jpeg;base64," + encoded,
                "width": original_size[0],
                "height": original_size[1],
                "elapsed_ms": round(elapsed, 1),
                "device": device,
                "model": folder.name,
            },
        )
        log(f"Найдено объектов: {len(detections)}")
        return

    logits = raw.reshape(-1)
    if logits.size < 2:
        emit("error", message="Выход модели не похож на классификатор.")
        return
    probabilities = softmax(logits)
    top_indices = probabilities.argsort()[::-1][:top_k]
    results = []
    for index in top_indices:
        index = int(index)
        results.append(
            {
                "label": (labels[index] if index < len(labels) else f"class {index}").replace("_", " "),
                "score": round(float(probabilities[index]), 4),
            }
        )
    emit(
        "result",
        data={
            "task": "classify",
            "predictions": results,
            "image": None,
            "width": original_size[0],
            "height": original_size[1],
            "elapsed_ms": round(elapsed, 1),
            "device": device,
            "model": folder.name,
        },
    )
    log(f"Топ-{len(results)}: " + ", ".join(f"{r['label']} {r['score']*100:.1f}%" for r in results))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback

        emit("error", message=f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        sys.exit(1)
