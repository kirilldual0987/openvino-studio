"""Probe OpenVINO runtime and devices. Prints one JSON object."""
from __future__ import annotations

import json
import os
import sys


def main() -> None:
    result = {
        "installed": False,
        "ov_version": "",
        "genai_version": "",
        "devices": [],
        "error": "",
        "cpu_name": "",
    }
    try:
        import openvino as ov

        result["installed"] = True
        result["ov_version"] = getattr(ov, "__version__", "")
        core = ov.Core()
        available = list(core.available_devices)
        result["devices"] = []
        for device in available:
            entry = {"id": device, "name": device, "type": "", "details": {}}
            for key in ("FULL_DEVICE_NAME", "DEVICE_TYPE", "DEVICE_ARCHITECTURE", "DEVICE_ID"):
                try:
                    entry["details"][key] = str(core.get_property(device, key))
                except Exception:
                    pass
            entry["name"] = entry["details"].get("FULL_DEVICE_NAME") or device
            entry["type"] = entry["details"].get("DEVICE_TYPE") or ""
            result["devices"].append(entry)
        try:
            result["cpu_name"] = str(core.get_property("CPU", "FULL_DEVICE_NAME"))
        except Exception:
            pass
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    try:
        import openvino_genai as ov_genai

        result["genai_version"] = getattr(ov_genai, "__version__", "")
    except Exception:
        pass
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
