import asyncio
import base64
import difflib
import io
import json
import os
import re
import time
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Header, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

# --- Configuration (all overridable via environment variables) ----------

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "deepseek-ocr:latest")
API_TOKEN = os.environ.get("API_TOKEN", "")  # empty = no auth required
MAX_MEGAPIXELS = float(os.environ.get("MAX_MEGAPIXELS", "1.0"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
MAX_SOURCE_MEGAPIXELS = float(os.environ.get("MAX_SOURCE_MEGAPIXELS", "20"))
NUM_CTX = int(os.environ.get("NUM_CTX", "8192"))
NUM_PREDICT = int(os.environ.get("NUM_PREDICT", "2048"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0"))
REPEAT_PENALTY = float(os.environ.get("REPEAT_PENALTY", "1.15"))
REPEAT_LAST_N = int(os.environ.get("REPEAT_LAST_N", "128"))
GEN_TIME_LIMIT = float(os.environ.get("GEN_TIME_LIMIT", "600"))
# httpx applies this as a "no data received for N seconds" stall guard on a
# streamed response, not a total-duration cap — GEN_TIME_LIMIT is what
# actually bounds how long a request takes overall.
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "900"))

TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "tesseract")
TESSERACT_LANGS = os.environ.get("TESSERACT_LANGS", "ukr+eng")
# Unlike the LLM, Tesseract needs detail (~300 DPI): an A4 page at 300 DPI is ~8.7 MP.
TESSERACT_MAX_MEGAPIXELS = float(os.environ.get("TESSERACT_MAX_MEGAPIXELS", "8"))
TESSERACT_TIMEOUT = float(os.environ.get("TESSERACT_TIMEOUT", "120"))

# Tesseract page segmentation mode per OCR mode: 3 = automatic layout,
# 6 = one uniform block read row by row (keeps table rows together),
# 11 = sparse text scattered around a figure.
TESSERACT_PSM = {"text": 3, "table": 6, "figure": 11, "document": 3}

MODE_PROMPTS = {
    "text": "Free OCR.",
    "table": "Parse the figure.",
    "figure": "Parse the figure.",
    "document": "<|grounding|>Convert the document to markdown.",
}

app = FastAPI(title="OCR service", version="1.0.0")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


# --- Helpers --------------------------------------------------------------

def check_auth(authorization: Optional[str]) -> None:
    if not API_TOKEN:
        return
    expected = f"Bearer {API_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Відсутній або невірний токен доступу")


def open_image(raw: bytes) -> Image.Image:
    """Open and decode an upload, rejecting oversized images before decoding
    the pixels so a huge image can't exhaust the Pi's RAM."""
    try:
        img = Image.open(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Не вдалося прочитати зображення. Деталі: {exc}"
        )

    width, height = img.size
    if (width * height) / 1_000_000 > MAX_SOURCE_MEGAPIXELS:
        raise HTTPException(
            status_code=413,
            detail=f"Зображення має бути не більше {MAX_SOURCE_MEGAPIXELS:g} МП",
        )

    try:
        img.load()
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Не вдалося прочитати зображення. Деталі: {exc}"
        )
    return img


def downscale_image(raw: bytes, max_megapixels: float) -> bytes:
    """Resize the image so it stays near the resolution the OCR model was trained on.
    Feeding it much larger images is the #1 cause of runaway token repetition."""
    img = open_image(raw)
    width, height = img.size
    megapixels = (width * height) / 1_000_000

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    if megapixels > max_megapixels:
        scale = (max_megapixels / megapixels) ** 0.5
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    return to_png(img)


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def find_skew_angle(img: Image.Image) -> float:
    """Find the angle (degrees, counter-clockwise) that levels slightly tilted
    text, e.g. a page photographed at an angle. When text rows are level, the
    ink per pixel row alternates sharply between lines and gaps; we rotate a
    small copy and keep the angle where that row profile is sharpest."""
    thumb = img.convert("L")
    thumb.thumbnail((600, 600))
    ink = thumb.point(lambda p: 255 if p < 128 else 0)  # text white on black

    def score(angle: float) -> tuple[float, float]:
        rotated = ink.rotate(angle, resample=Image.BILINEAR, fillcolor=0)
        rows = rotated.resize((1, rotated.height), Image.BOX).tobytes()
        mean = sum(rows) / len(rows)
        # Ties (e.g. a blank page) go to the smallest rotation.
        return sum((v - mean) ** 2 for v in rows), -abs(angle)

    # ponytail: brute-force search (~30 small rotations), fine for ±10° tilt;
    # widen the range if steeper photos show up.
    best = max(range(-10, 11), key=score)
    return max((best + step / 10 for step in range(-5, 6)), key=score)


def straighten(img: Image.Image) -> Image.Image:
    angle = find_skew_angle(img)
    if abs(angle) < 0.3:  # not worth resampling the image
        return img
    return img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)


def turn_upright(image_png: bytes, clockwise: int) -> bytes:
    """Turn a prepared (grayscale) page by the OSD-detected rotation, then
    level any small tilt that was hidden while the page lay sideways."""
    img = Image.open(io.BytesIO(image_png)).rotate(-clockwise, expand=True)
    return to_png(straighten(img))


def prepare_for_tesseract(raw: bytes, max_megapixels: float) -> bytes:
    """Clean up an image for Tesseract: upright, grayscale, high contrast, and
    at a resolution close to a 300 DPI scan."""
    img = ImageOps.exif_transpose(open_image(raw))  # phone photos are often rotated

    # Converting straight to grayscale turns transparent pixels black, which
    # hides black text, so flatten transparency onto white first.
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        img = Image.alpha_composite(
            Image.new("RGBA", img.size, "white"), img.convert("RGBA")
        )
    img = ImageOps.autocontrast(img.convert("L"))

    width, height = img.size
    megapixels = (width * height) / 1_000_000
    # Small images (e.g. photos compressed by a messenger) have text too small
    # to read; enlarging them up to 2x roughly doubles the phrases recognized.
    target = min(4.0, max_megapixels)
    if megapixels > max_megapixels:
        scale = (max_megapixels / megapixels) ** 0.5
    elif megapixels < target:
        scale = min(2.0, (target / megapixels) ** 0.5)
    else:
        scale = 1.0
    if scale != 1.0:
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    return to_png(straighten(img))


async def detect_rotation(image_png: bytes) -> int:
    """Ask Tesseract's orientation check (OSD) whether the page is sideways
    or upside down, which EXIF can't tell for photos sent via messengers
    (they strip it). Returns degrees to turn clockwise: 0, 90, 180 or 270.
    OSD fails on pages with little text, so any failure just means 0."""
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            TESSERACT_CMD, "stdin", "stdout", "--psm", "0",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(image_png), 30)
    except (OSError, TimeoutError):
        return 0
    finally:
        if proc is not None and proc.returncode is None:  # timed out or Stop pressed
            proc.kill()
            await proc.wait()

    text = out.decode("utf-8", errors="replace")
    rotate = re.search(r"Rotate: (\d+)", text)
    confidence = re.search(r"Orientation confidence: ([\d.]+)", text)
    # Low confidence guesses flip upright pages, so only trust clear answers.
    if proc.returncode != 0 or not rotate or not confidence or float(confidence.group(1)) < 2:
        return 0
    return int(rotate.group(1)) % 360


async def tesseract_ocr(
    raw: bytes, mode: str, max_megapixels: float, renderer: Optional[str] = None
) -> bytes:
    """Returns Tesseract's raw output: plain text by default, or the file of
    the given renderer ("tsv" = words with confidence)."""
    # Image work runs in a thread so a big photo doesn't stall other requests.
    image_png = await asyncio.to_thread(prepare_for_tesseract, raw, max_megapixels)
    rotation = await detect_rotation(image_png)
    if rotation:
        image_png = await asyncio.to_thread(turn_upright, image_png, rotation)
    return await run_tesseract(image_png, mode, renderer)


async def run_tesseract(image_png: bytes, mode: str, renderer: Optional[str] = None) -> bytes:
    """Run the tesseract CLI on a PNG passed through stdin (no temp files, so
    patient documents never touch the disk)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            TESSERACT_CMD, "stdin", "stdout",
            "-l", TESSERACT_LANGS,
            "--psm", str(TESSERACT_PSM[mode]),
            "-c", "preserve_interword_spaces=1",
            *([renderer] if renderer else []),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"Tesseract не встановлено на сервері. Деталі: '{TESSERACT_CMD}' not found",
        )

    try:
        out, err = await asyncio.wait_for(proc.communicate(image_png), TESSERACT_TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise HTTPException(
            status_code=504,
            detail=f"Tesseract не завершив розпізнавання за {TESSERACT_TIMEOUT:.0f} с",
        )
    except asyncio.CancelledError:  # the browser pressed Stop
        proc.kill()
        await proc.wait()
        raise

    if proc.returncode != 0:
        details = err.decode("utf-8", errors="replace").strip()[:500]
        raise HTTPException(
            status_code=502,
            detail=f"Tesseract не зміг розпізнати зображення. Деталі: {details}",
        )
    return out


def clean_tesseract_text(text: str) -> str:
    """Drop form feeds and trailing spaces; keep at most two blank lines in a row."""
    lines = [line.rstrip() for line in text.replace("\f", "").splitlines()]
    return re.sub(r"\n{4,}", "\n\n\n", "\n".join(lines)).strip()


async def tesseract_status() -> dict:
    """Report whether tesseract runs and has every language from TESSERACT_LANGS."""
    wanted = TESSERACT_LANGS.split("+")
    status = {"available": False, "version": None, "langs": [], "missing_langs": wanted}

    async def run(*args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            TESSERACT_CMD, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # older versions print to stderr
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), 10)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        return out.decode("utf-8", errors="replace")

    try:
        version = await run("--version")
        langs = await run("--list-langs")
    except (OSError, TimeoutError):
        return status

    # "--list-langs" prints a "List of available languages ..." header first.
    status["langs"] = [l.strip() for l in langs.splitlines()[1:] if l.strip()]
    status["missing_langs"] = [l for l in wanted if l not in status["langs"]]
    status["version"] = version.splitlines()[0].strip() if version.strip() else None
    status["available"] = not status["missing_langs"]
    return status


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
    """Some images push the OCR model into repeating the same sentence(s) forever —
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


async def cancel_on_disconnect(request: Request, coro):
    """Run an OCR coroutine, cancelling it once the browser disconnects (the
    UI's Stop button). Polling here, not inside the OCR loop, also covers the
    minutes Ollama can spend loading the model before the first token."""
    task = asyncio.ensure_future(coro)
    while True:
        done, _ = await asyncio.wait({task}, timeout=1)
        if done:
            return task.result()
        if await request.is_disconnected():
            task.cancel()  # closes the Ollama stream / kills tesseract
            await asyncio.gather(task, return_exceptions=True)
            raise HTTPException(status_code=499, detail="Запит скасовано клієнтом")


async def run_ocr(image_bytes: bytes, mode: str, max_predict: int) -> tuple[str, str]:
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
            "num_predict": max_predict,
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
                        detail=f"Ollama повернула помилку {resp.status_code}. Деталі: {body[:500]}",
                    )

                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if "error" in obj:
                        raise HTTPException(
                            status_code=502, detail=f"Помилка Ollama. Деталі: {obj['error']}"
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
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=(
                f"Ollama не відповіла за {REQUEST_TIMEOUT:.0f} с. Модель може ще "
                "завантажуватись або запит завеликий."
            ),
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Не вдалося з'єднатися з Ollama ({OLLAMA_HOST}). Деталі: {exc}",
        )

    return "".join(chunks), stop_reason


# --- Endpoints --------------------------------------------------------------

@app.get("/health")
async def health():
    # Reported even when Ollama is down: Tesseract alone keeps the service usable.
    tesseract = await tesseract_status()
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags")
            resp.raise_for_status()
            tags = [m["name"] for m in resp.json().get("models", [])]
            model_ready = any(t.startswith(OLLAMA_MODEL.split(":")[0]) for t in tags)
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "ollama_unreachable",
                    "detail": str(exc),
                    "tesseract": tesseract,
                },
            )

    return {
        "status": "ok",
        "ollama_host": OLLAMA_HOST,
        "model": OLLAMA_MODEL,
        "model_pulled": model_ready,
        "known_models": tags,
        "tesseract": tesseract,
    }


def _ocr_response(
    *,
    text: str,
    mode: str,
    engine: str,
    model: str,
    elapsed: float,
    filename: Optional[str],
    truncated: bool,
    warning: Optional[str],
    output: str,
):
    if output == "text":
        return PlainTextResponse(text)

    return {
        "text": text,
        "mode": mode,
        "engine": engine,
        "model": model,
        "seconds": elapsed,
        "filename": filename,
        "truncated": truncated,
        "warning": warning,
    }


@app.post("/ocr")
async def ocr(
    request: Request,
    file: UploadFile = File(...),
    mode: Literal["text", "table", "figure", "document"] = Form("text"),
    output: Literal["text", "json", "tsv"] = Form("json"),
    engine: Literal["deepseek", "tesseract"] = Form("deepseek"),
    max_megapixels: Optional[float] = Form(None),
    max_predict: Optional[int] = Form(None),
    authorization: Optional[str] = Header(None),
):
    check_auth(authorization)

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Порожній файл")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Файл має бути не більше {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ",
        )

    if max_megapixels is not None and max_megapixels <= 0:
        raise HTTPException(status_code=400, detail="max_megapixels має бути більше 0")

    if max_predict is not None and not 64 <= max_predict <= NUM_PREDICT:
        raise HTTPException(
            status_code=400,
            detail=f"max_predict має бути від 64 до {NUM_PREDICT}",
        )

    if engine == "tesseract":
        # max_predict is a DeepSeek setting and is ignored here.
        renderer = "tsv" if output == "tsv" else None
        started = time.time()
        out = await cancel_on_disconnect(
            request,
            tesseract_ocr(raw, mode, max_megapixels or TESSERACT_MAX_MEGAPIXELS, renderer),
        )
        if output == "tsv":
            return PlainTextResponse(
                out.decode("utf-8", errors="replace"),
                media_type="text/tab-separated-values",
            )
        return _ocr_response(
            text=clean_tesseract_text(out.decode("utf-8", errors="replace")),
            mode=mode,
            engine=engine,
            model=f"tesseract ({TESSERACT_LANGS})",
            elapsed=round(time.time() - started, 2),
            filename=file.filename,
            truncated=False,
            warning=None,
            output=output,
        )

    if output == "tsv":
        raise HTTPException(status_code=400, detail="output=tsv доступний лише для Tesseract")

    limit = max_megapixels if max_megapixels else MAX_MEGAPIXELS
    resized = await asyncio.to_thread(downscale_image, raw, limit)

    started = time.time()
    text, stop_reason = await cancel_on_disconnect(
        request, run_ocr(resized, mode, max_predict or NUM_PREDICT)
    )
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
            "Текст обрізано: модель досягла ліміту токенів. Для довгого документа "
            "обери деталізацію «Висока» (до 2048 токенів) або обріж зображення до потрібної частини."
        )
    else:
        warning = None

    return _ocr_response(
        text=text,
        mode=mode,
        engine=engine,
        model=OLLAMA_MODEL,
        elapsed=elapsed,
        filename=file.filename,
        truncated=truncated,
        warning=warning,
        output=output,
    )


@app.get("/api")
async def api_info():
    return {
        "service": "ocr-service",
        "endpoints": {
            "GET /": "web interface — upload an image, get copiable text",
            "POST /ocr": "multipart form: file, mode=text|table|figure|document, output=json|text|tsv (tsv: Tesseract only), engine=deepseek|tesseract, max_megapixels, max_predict (DeepSeek only)",
            "GET /health": "checks Ollama (and whether the model is pulled) and Tesseract languages",
        },
    }


@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
