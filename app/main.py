import base64
import difflib
import io
import json
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
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "AuditAid/PaddleOCR-VL-1.6-0.9B:latest")
API_TOKEN = os.environ.get("API_TOKEN", "")  # empty = no auth required
MAX_MEGAPIXELS = float(os.environ.get("MAX_MEGAPIXELS", "1.0"))
NUM_CTX = int(os.environ.get("NUM_CTX", "8192"))
NUM_PREDICT = int(os.environ.get("NUM_PREDICT", "2048"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0"))
REPEAT_PENALTY = float(os.environ.get("REPEAT_PENALTY", "1.15"))
REPEAT_LAST_N = int(os.environ.get("REPEAT_LAST_N", "128"))
GEN_TIME_LIMIT = float(os.environ.get("GEN_TIME_LIMIT", "90"))
# httpx applies this as a "no data received for N seconds" stall guard on a
# streamed response, not a total-duration cap — GEN_TIME_LIMIT is what
# actually bounds how long a request takes overall.
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "180"))

MODE_PROMPTS = {
    # PaddleOCR-VL's own documented element-level task prompts — plain
    # strings, not chat/markdown instructions. Each one switches the model
    # into a dedicated recognition head for that content type.
    "text": "OCR:",
    "table": "Table Recognition:",
    "figure": "Chart Recognition:",
    # Not one of PaddleOCR-VL's documented fixed prompts — this is a plain
    # instruction to the underlying ERNIE language model, asking it to
    # reproduce the page as structured Markdown instead of flat text. It's
    # a single-pass, whole-image guess at layout (headings, lists, bold,
    # tables), not the real bounding-box-based layout detection that
    # PaddleOCR's own page-level `doc_parser` pipeline does — so it works
    # well for simple documents but won't precisely reconstruct complex
    # multi-column layouts.
    "document": (
        "Convert this document to Markdown. Preserve the structure: use "
        "# / ## / ### for headings, - or 1. for lists, **bold** / *italic* "
        "for emphasis, and Markdown tables for tabular data. Output only "
        "the Markdown, no explanations or code fences."
    ),
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


def strip_markdown_fence(text: str) -> str:
    """Models sometimes wrap Markdown output in a ```markdown ... ``` code
    fence despite being told not to — strip it so the result is plain,
    directly-renderable Markdown."""
    stripped = text.strip()
    match = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", stripped, re.DOTALL)
    return match.group(1) if match else stripped


def _similar(a: str, b: str, threshold: float = 0.88) -> bool:
    if not a or not b:
        return a == b
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def collapse_repetition(text: str, min_streak: int = 4) -> tuple[str, bool]:
    """Some images push GLM-OCR into repeating the same sentence(s) forever —
    this happens even with sampling penalties tuned up, and even via raw
    `ollama run` with no options set at all. As a last line of defense,
    detect a block of 1-4 sentences that repeats several times in a row and
    cut the text right after its first clean occurrence, so the copied
    result is usable regardless of whether the underlying loop was
    preventable.

    The repeats are often NOT byte-identical — the model tends to drift
    slightly each time (small transliteration/spelling changes), so this
    compares blocks with fuzzy similarity (difflib) rather than exact
    equality; an exact-match check misses most real-world loops.

    Requires min_streak (4) consecutive near-duplicate blocks, not just 2-3
    — genuine loops run for many cycles, while legitimate structured text
    (an invoice's line items, say, which can look deceptively similar to
    each other) rarely has 4+ near-identical lines back to back. This
    keeps the false-positive rate low without missing real loops."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s for s in sentences if s.strip()]
    norm = [re.sub(r"\s+", " ", s).strip().lower() for s in sentences]
    n = len(norm)

    for block in range(1, 5):
        i = 0
        while i + min_streak * block <= n:
            chunks = [
                " ".join(norm[i + k * block : i + (k + 1) * block])
                for k in range(min_streak)
            ]
            if len(chunks[0]) >= 20 and all(
                _similar(chunks[k], chunks[k + 1]) for k in range(min_streak - 1)
            ):
                kept = sentences[: i + block]
                return " ".join(kept).strip(), True
            i += 1

    return text, False


async def run_ocr(image_bytes: bytes, mode: str) -> tuple[str, str]:
    """Streams the response from Ollama instead of waiting for the whole
    thing at once. This lets us enforce a wall-clock time limit on
    generation (GEN_TIME_LIMIT) rather than only a token-count limit
    (NUM_PREDICT) — useful because generation speed varies a lot between
    machines (a Pi vs. a Mac, CPU vs. GPU), so a token cap alone gives no
    guarantee on how long a request actually takes. If the time limit is
    hit, we close the connection (which cancels the request on Ollama's
    side) and return whatever text was generated so far, instead of
    throwing it all away like a plain request timeout would.

    Returns (text, stop_reason): stop_reason is "stop" (finished
    naturally), "length" (hit num_predict) or "time_limit" (we cut it
    off after GEN_TIME_LIMIT seconds).
    """
    prompt = MODE_PROMPTS.get(mode, MODE_PROMPTS["text"])
    b64 = base64.b64encode(image_bytes).decode("ascii")

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "images": [b64],
        "stream": True,
        "options": {
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
            "temperature": TEMPERATURE,
            "repeat_penalty": REPEAT_PENALTY,
            "repeat_last_n": REPEAT_LAST_N,
        },
    }

    chunks: list[str] = []
    stop_reason = "stop"
    started = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            async with client.stream(
                "POST", f"{OLLAMA_HOST}/api/generate", json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise HTTPException(
                        status_code=502,
                        detail=f"Ollama returned {resp.status_code}: {body[:500]}",
                    )

                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if "error" in obj:
                        raise HTTPException(
                            status_code=502, detail=f"Ollama error: {obj['error']}"
                        )

                    chunks.append(obj.get("response", ""))

                    if obj.get("done"):
                        stop_reason = obj.get("done_reason", "stop")
                        break

                    if time.monotonic() - started > GEN_TIME_LIMIT:
                        stop_reason = "time_limit"
                        break
                # Leaving this block closes the connection; if we broke out
                # early, that tells Ollama to cancel the in-progress request
                # instead of letting it keep burning CPU in the background.
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach Ollama at {OLLAMA_HOST}: {exc}",
        )

    return "".join(chunks), stop_reason


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
    mode: Literal["text", "table", "figure", "document"] = Form("text"),
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
    text, stop_reason = await run_ocr(resized, mode)
    elapsed = round(time.time() - started, 2)

    if mode == "document":
        text = strip_markdown_fence(text)

    repetition_collapsed = False
    if mode not in ("table", "document"):
        # Structured content — a table's repeated rows, or a document's
        # repeated list items/headings — can legitimately look like a
        # repetition loop to collapse_repetition, so skip it here.
        text, repetition_collapsed = collapse_repetition(text)

    truncated = repetition_collapsed or stop_reason in ("length", "time_limit")

    if repetition_collapsed:
        warning = (
            "Модель почала повторювати той самий фрагмент — текст обрізано "
            "одразу після першого чистого входження. Перевір результат; якщо "
            "бракує частини, спробуй зменшити max_megapixels."
        )
    elif stop_reason == "time_limit":
        warning = (
            f"Розпізнавання перевищило ліміт часу ({GEN_TIME_LIMIT:.0f} с) і було "
            "перервано — текст може бути неповним. Якщо це просто великий документ, "
            "піднімай GEN_TIME_LIMIT; якщо це зациклення, спробуй зменшити max_megapixels."
        )
    elif stop_reason == "length":
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
            "POST /ocr": "multipart form: file, mode=text|table|figure|document, output=json|text",
            "GET /health": "checks connectivity to Ollama and whether the model is pulled",
        },
    }


@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
