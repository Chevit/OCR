import base64
import io
import os
import re
import time
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Header, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

# --- Configuration (all overridable via environment variables) ----------

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "glm-ocr:latest")
API_TOKEN = os.environ.get("API_TOKEN", "")  # empty = no auth required
MAX_MEGAPIXELS = float(os.environ.get("MAX_MEGAPIXELS", "1.0"))
NUM_CTX = int(os.environ.get("NUM_CTX", "8192"))
NUM_PREDICT = int(os.environ.get("NUM_PREDICT", "2048"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0"))
REPEAT_PENALTY = float(os.environ.get("REPEAT_PENALTY", "1.15"))
REPEAT_LAST_N = int(os.environ.get("REPEAT_LAST_N", "128"))
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "480"))

MODE_PROMPTS = {
    "text": "Text Recognition:",
    "table": "Table Recognition:",
    "figure": "Figure Recognition:",
}

app = FastAPI(title="GLM-OCR service", version="1.0.0")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


# --- Helpers --------------------------------------------------------------

def check_auth(authorization: Optional[str]) -> None:
    if not API_TOKEN:
        return
    expected = f"Bearer {API_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token")


def downscale_image(raw: bytes, max_megapixels: float) -> bytes:
    """Resize the image so it stays near the resolution GLM-OCR was trained on.
    Feeding it much larger images is the #1 cause of runaway token repetition."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read image: {exc}")

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    width, height = img.size
    megapixels = (width * height) / 1_000_000
    if megapixels > max_megapixels:
        scale = (max_megapixels / megapixels) ** 0.5
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def collapse_repetition(text: str) -> tuple[str, bool]:
    """Some images push GLM-OCR into repeating the same sentence(s) forever —
    this happens even with sampling penalties tuned up, and even via raw
    `ollama run` with no options set at all. As a last line of defense,
    detect a block of 1-4 sentences that repeats 3+ times in a row and cut
    the text right after its first clean occurrence, so the copied result
    is usable regardless of whether the underlying loop was preventable."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s for s in sentences if s.strip()]
    norm = [re.sub(r"\s+", " ", s).strip().lower() for s in sentences]
    n = len(norm)

    for block in range(1, 5):
        i = 0
        while i + 3 * block <= n:
            a = norm[i : i + block]
            b = norm[i + block : i + 2 * block]
            c = norm[i + 2 * block : i + 3 * block]
            if a == b == c and len(" ".join(a)) >= 20:
                kept = sentences[: i + block]
                return " ".join(kept).strip(), True
            i += 1

    return text, False


async def run_ocr(image_bytes: bytes, mode: str) -> tuple[str, bool]:
    prompt = MODE_PROMPTS.get(mode, MODE_PROMPTS["text"])
    b64 = base64.b64encode(image_bytes).decode("ascii")

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "images": [b64],
        "stream": False,
        "options": {
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
            "temperature": TEMPERATURE,
            "repeat_penalty": REPEAT_PENALTY,
            "repeat_last_n": REPEAT_LAST_N,
        },
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            resp = await client.post(f"{OLLAMA_HOST}/api/generate", json=payload)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Could not reach Ollama at {OLLAMA_HOST}: {exc}",
            )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama returned {resp.status_code}: {resp.text[:500]}",
        )

    data = resp.json()
    if "error" in data:
        raise HTTPException(status_code=502, detail=f"Ollama error: {data['error']}")

    text = data.get("response", "")
    length_capped = data.get("done_reason") == "length"
    return text, length_capped


# --- Endpoints --------------------------------------------------------------

@app.get("/health")
async def health():
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags")
            resp.raise_for_status()
            tags = [m["name"] for m in resp.json().get("models", [])]
            model_ready = any(t.startswith(OLLAMA_MODEL.split(":")[0]) for t in tags)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"status": "ollama_unreachable", "detail": str(exc)},
            )

    return {
        "status": "ok",
        "ollama_host": OLLAMA_HOST,
        "model": OLLAMA_MODEL,
        "model_pulled": model_ready,
        "known_models": tags,
    }


@app.post("/ocr")
async def ocr(
    file: UploadFile = File(...),
    mode: Literal["text", "table", "figure"] = Form("text"),
    output: Literal["text", "json"] = Form("json"),
    max_megapixels: Optional[float] = Form(None),
    authorization: Optional[str] = Header(None),
):
    check_auth(authorization)

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file upload")

    limit = max_megapixels if max_megapixels else MAX_MEGAPIXELS
    resized = downscale_image(raw, limit)

    started = time.time()
    text, length_capped = await run_ocr(resized, mode)
    elapsed = round(time.time() - started, 2)

    repetition_collapsed = False
    if mode != "table":
        text, repetition_collapsed = collapse_repetition(text)

    truncated = length_capped or repetition_collapsed
    if repetition_collapsed:
        warning = (
            "Модель почала повторювати той самий фрагмент — текст обрізано "
            "одразу після першого чистого входження. Перевір результат; якщо "
            "бракує частини, спробуй зменшити max_megapixels."
        )
    elif length_capped:
        warning = (
            "Модель впиралась у ліміт токенів — ймовірно почала повторюватись. "
            "Спробуй зменшити max_megapixels або обрізати зображення до самого тексту."
        )
    else:
        warning = None

    if output == "text":
        return PlainTextResponse(text)

    return {
        "text": text,
        "mode": mode,
        "model": OLLAMA_MODEL,
        "seconds": elapsed,
        "filename": file.filename,
        "truncated": truncated,
        "warning": warning,
    }


@app.get("/api")
async def api_info():
    return {
        "service": "glm-ocr-service",
        "endpoints": {
            "GET /": "web interface — upload an image, get copiable text",
            "POST /ocr": "multipart form: file, mode=text|table|figure, output=json|text",
            "GET /health": "checks connectivity to Ollama and whether the model is pulled",
        },
    }


@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
