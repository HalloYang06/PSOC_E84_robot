import base64
import io
import os
import threading
from typing import Optional

import torch
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel
from transformers import AutoModelForVision2Seq, AutoProcessor

app = FastAPI(title="OpenVLA Local API")

MODEL_ID = os.getenv("OPENVLA_MODEL_ID", "openvla/openvla-7b")
HOST = os.getenv("OPENVLA_HOST", "0.0.0.0")
PORT = int(os.getenv("OPENVLA_PORT", "8000"))
UNNORM_KEY = os.getenv("OPENVLA_UNNORM_KEY", "bridge_orig")

_processor = None
_model = None
_model_error: Optional[str] = None
_model_status = "idle"
_model_lock = threading.Lock()


def _has_cuda() -> bool:
    return torch.cuda.is_available()


def _model_dtype() -> torch.dtype:
    if _has_cuda() and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    if _has_cuda():
        return torch.float16
    return torch.float32


def _should_use_4bit() -> bool:
    env_value = os.getenv("OPENVLA_LOAD_IN_4BIT")
    if env_value is not None:
        return env_value.lower() in {"1", "true", "yes", "on"}

    if not _has_cuda():
        return False

    total_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    return total_vram_gb <= 12


def _load_model() -> None:
    global _processor, _model, _model_error, _model_status

    with _model_lock:
        if _model is not None or _model_status == "loading":
            return
        _model_status = "loading"
        _model_error = None

    try:
        model_kwargs = {
            "torch_dtype": _model_dtype(),
            "low_cpu_mem_usage": True,
            "trust_remote_code": True,
        }
        if _has_cuda():
            model_kwargs["device_map"] = "auto"
            if _should_use_4bit():
                model_kwargs["load_in_4bit"] = True

        print(f"Loading model {MODEL_ID} ...")
        processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
        model = AutoModelForVision2Seq.from_pretrained(MODEL_ID, **model_kwargs)

        with _model_lock:
            _processor = processor
            _model = model
            _model_status = "ready"

        print("Model is ready.")
    except Exception as exc:
        with _model_lock:
            _model_error = str(exc)
            _model_status = "error"
        print(f"Model load failed: {exc}")


@app.on_event("startup")
async def startup_event() -> None:
    threading.Thread(target=_load_model, daemon=True).start()


class RequestData(BaseModel):
    image_base64: str
    instruction: str


@app.get("/")
async def index():
    return {
        "service": "openvla",
        "status": _model_status,
        "model_id": MODEL_ID,
        "cuda_available": _has_cuda(),
        "load_in_4bit": _should_use_4bit(),
        "act_endpoint": "/act",
        "health_endpoint": "/healthz",
        "error": _model_error,
    }


@app.get("/healthz")
async def healthz():
    if _model_status == "ready":
        return {"status": "ok"}
    if _model_status == "error":
        raise HTTPException(status_code=500, detail=_model_error)
    raise HTTPException(status_code=503, detail=f"Model status: {_model_status}")


@app.post("/act")
async def get_action(data: RequestData):
    if _model is None or _processor is None:
        detail = _model_error or f"Model status: {_model_status}"
        raise HTTPException(status_code=503, detail=detail)

    try:
        img_data = base64.b64decode(data.image_base64)
        image = Image.open(io.BytesIO(img_data)).convert("RGB")

        prompt = f"In: What action should the robot take to {data.instruction}?\nOut:"
        inputs = _processor(prompt, image).to("cuda" if _has_cuda() else "cpu", dtype=_model_dtype())

        with torch.inference_mode():
            action = _model.predict_action(**inputs, unnorm_key=UNNORM_KEY, do_sample=False)

        return {"action": action.tolist()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
