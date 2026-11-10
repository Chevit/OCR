import asyncio
import base64
import io
import os
import re
import time
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, Header, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageFilter, ImageMath, ImageOps, ImageStat

# --- Configuration (all overridable via environment variables) ----------

API_TOKEN = os.environ.get("API_TOKEN", "")  # empty = no auth required
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
MAX_SOURCE_MEGAPIXELS = float(os.environ.get("MAX_SOURCE_MEGAPIXELS", "20"))

TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "tesseract")
TESSERACT_LANGS = os.environ.get("TESSERACT_LANGS", "ukr+eng")
# Tesseract needs detail (~300 DPI): an A4 page at 300 DPI is ~8.7 MP.
TESSERACT_MAX_MEGAPIXELS = float(os.environ.get("TESSERACT_MAX_MEGAPIXELS", "8"))
TESSERACT_TIMEOUT = float(os.environ.get("TESSERACT_TIMEOUT", "120"))
# Recognitions running at once; the rest wait their turn. Each one gets a single
# CPU thread (OMP_THREAD_LIMIT), so the default fills a 4-core Pi 5 exactly.
OCR_CONCURRENCY = int(os.environ.get("OCR_CONCURRENCY", "4"))
TESSERACT_ENV = {**os.environ, "OMP_THREAD_LIMIT": "1"}
OCR_SLOTS = asyncio.Semaphore(OCR_CONCURRENCY)

# Models from tessdata_best: slower, usually more accurate. The default
# (fast) models come with the tesseract packages; the image adds these.
TESSDATA_BEST_DIR = os.environ.get("TESSDATA_BEST_DIR", "/usr/share/tessdata_best")

# Tesseract page segmentation mode per OCR mode: 3 = automatic layout,
# 6 = one uniform block read row by row (keeps table rows together; also
# reads a cropped fragment better than 3, see tests/bench/RESULTS.md (11)).
TESSERACT_PSM = {"text": 3, "table": 6, "block": 6}

# Image preparation: "v2" evens out shadows and uneven light and sizes pages
# by their text height; "baseline" (the old way) sizes them by megapixels.
# ponytail: baseline stays only until the holdout benchmark confirms v2.
PREPROCESS = os.environ.get("PREPROCESS", "v2")
if PREPROCESS not in ("baseline", "v2"):
    raise RuntimeError(f"PREPROCESS must be baseline or v2, not {PREPROCESS!r}")
# Glyph height (px) Tesseract's LSTM models read best; v2 scales to it.
TEXT_HEIGHT_PX = 30
# 1 = fix Latin/Cyrillic look-alike letters inside words, letters read
# instead of digits in numbers, dates and ICD-10 codes, and ICD-10 codes'
# letter and spacing (fix_icd10).
POSTPROCESS = os.environ.get("POSTPROCESS", "0") == "1"

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


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def find_skew_angle(img: Image.Image) -> float:
    """Find the angle (degrees, counter-clockwise) that levels slightly tilted
    text, e.g. a page photographed at an angle. When text rows are level, the
    ink per pixel row alternates sharply between lines and gaps; we rotate a
    small copy and keep the angle where that row profile is sharpest. Only
    the central 70% is measured: the edges of a page lying on a desk are
    long slanted lines that would outvote the text."""
    w, h = img.size
    thumb = img.convert("L").crop((int(w * 0.15), int(h * 0.15), int(w * 0.85), int(h * 0.85)))
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


def straighten(img: Image.Image, angle: Optional[float] = None) -> Image.Image:
    if angle is None:
        angle = find_skew_angle(img)
    if abs(angle) < 0.3:  # not worth resampling the image
        return img
    # Fill the new corners with the paper's gray, not white: white corners on
    # a gray photographed page make Tesseract's Otsu threshold black out the
    # whole sheet (image-17). The 90th percentile is the paper, not the text
    # or dark surroundings; on a flattened (v2) page it is about white.
    return img.rotate(angle, resample=Image.BICUBIC, expand=True,
                      fillcolor=paper_level(img))


def paper_level(img: Image.Image) -> int:
    """90th-percentile gray of a grayscale image."""
    hist = img.histogram()
    count, needed = 0, 0.9 * sum(hist)
    for level, n in enumerate(hist):
        count += n
        if count >= needed:
            return level
    return 255


def turn_upright(image_png: bytes, clockwise: int) -> bytes:
    """Turn a prepared (grayscale) page by the OSD-detected rotation, then
    level any small tilt that was hidden while the page lay sideways."""
    img = Image.open(io.BytesIO(image_png)).rotate(-clockwise, expand=True)
    return to_png(straighten(img))


def flatten_background(img: Image.Image) -> Image.Image:
    """Even out shadows and uneven light in a photo. A max filter on a small
    copy erases the (darker) text and leaves the page background with its
    lighting; dividing by it leaves the text on even white."""
    small = img.copy()
    small.thumbnail((512, 512), Image.BOX)
    background = (
        small.filter(ImageFilter.MaxFilter(15))
        .filter(ImageFilter.GaussianBlur(5))
        .resize(img.size, Image.BILINEAR)
        .point(lambda v: max(v, 1))  # no division by zero
    )
    return ImageMath.lambda_eval(
        lambda a: a["convert"](a["float"](a["page"]) * 255 / a["bg"], "L"),
        page=img, bg=background,
    )


def line_pitch(img: Image.Image, angle: float) -> Optional[float]:
    """Distance between text lines in img's pixels, from the period of the
    ink-per-row profile of a ~1500 px copy levelled by the skew angle.
    None when no clear period stands out (little text, pictures)."""
    copy = img.copy()
    copy.thumbnail((1500, 1500), Image.BOX)
    ink = copy.point(lambda p: 255 if p < 128 else 0)
    ink = ink.rotate(angle, resample=Image.BILINEAR, expand=True, fillcolor=0)
    rows = ink.resize((1, ink.height), Image.BOX).tobytes()
    mean = sum(rows) / len(rows)
    rows = [v - mean for v in rows]

    def corr(lag: int) -> float:
        return sum(a * b for a, b in zip(rows, rows[lag:]))

    energy = corr(0)
    lags = range(6, len(rows) // 3)
    if not energy or not lags:
        return None
    # ponytail: O(rows x lags) pure-Python autocorrelation, ~0.1 s on a 1500 px
    # copy; switch to an FFT if bigger copies are ever needed.
    ac = {lag: corr(lag) for lag in lags}
    # Only clear peaks count: a slow trend (a dark table around the page)
    # makes the correlation fall steadily without being a period.
    peaks = [l for l in lags[1:-1]
             if ac[l - 1] < ac[l] >= ac[l + 1] and ac[l] >= 0.25 * energy]
    if not peaks:
        return None
    # Multiples of the line pitch (two lines, three) peak too; take the
    # shortest peak that is nearly as strong as the strongest.
    strongest = max(ac[l] for l in peaks)
    pitch = min(l for l in peaks if ac[l] >= 0.8 * strongest)
    return pitch * img.width / copy.width


def prepare_for_tesseract(
    raw: bytes, max_megapixels: float, preprocess: Optional[str] = None
) -> bytes:
    """Clean up an image for Tesseract: upright, grayscale, high contrast, and
    at a resolution close to a 300 DPI scan (v2: text about 30 px high)."""
    img = ImageOps.exif_transpose(open_image(raw))  # phone photos are often rotated

    # Converting straight to grayscale turns transparent pixels black, which
    # hides black text, so flatten transparency onto white first.
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        img = Image.alpha_composite(
            Image.new("RGBA", img.size, "white"), img.convert("RGBA")
        )
    img = ImageOps.autocontrast(img.convert("L"))
    # Light text on a dark background (dark-theme screenshots): Tesseract and
    # the tilt check both expect dark text on light, so flip mostly-dark images.
    if ImageStat.Stat(img).mean[0] < 128:
        img = ImageOps.invert(img)

    v2 = (preprocess or PREPROCESS) == "v2"
    angle = None
    if v2:
        img = ImageOps.autocontrast(flatten_background(img))

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
    if v2:
        angle = find_skew_angle(img)
        pitch = line_pitch(img, angle)
        if pitch:
            # Lines are ~1.5-2x the glyph height. Scale to the target height,
            # at most 2x up and within max_megapixels. A pitch misread as a
            # multiple of the line spacing asks for a shrink, so text height
            # may only shrink pages over max_megapixels (at most 2x); smaller
            # pages never get below the megapixel scale.
            floor = 0.5 if megapixels > max_megapixels else scale
            scale = min(2.0, (max_megapixels / megapixels) ** 0.5,
                        max(floor, TEXT_HEIGHT_PX / (pitch / 1.75)))
    if scale != 1.0:
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    return to_png(straighten(img, angle))


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
            env=TESSERACT_ENV,
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
    raw: bytes, mode: str, max_megapixels: float, renderer: Optional[str] = None,
    model: str = "fast",
) -> tuple[bytes, bytes]:
    """Returns Tesseract's raw output (plain text by default, or the file of
    the given renderer: "tsv" = words with confidence and position) and the
    prepared PNG it read, which word positions refer to."""
    # The whole job holds a slot, so CPU and RAM stay bounded; extra requests wait.
    async with OCR_SLOTS:
        # Image work runs in a thread so a big photo doesn't stall other requests.
        image_png = await asyncio.to_thread(prepare_for_tesseract, raw, max_megapixels)
        image_png = await make_upright(image_png)
        return await run_tesseract(image_png, mode, renderer, model), image_png


def mean_word_confidence(tsv: str) -> float:
    """Mean Tesseract confidence of the recognized words in a TSV; 0 if none."""
    confs = [
        float(c[10]) for c in (row.split("\t") for row in tsv.splitlines())
        if len(c) == 12 and c[0] == "5" and c[11].strip() and float(c[10]) >= 0
    ]
    return sum(confs) / len(confs) if confs else 0.0


async def make_upright(image_png: bytes) -> bytes:
    """Turn the prepared page by the orientation check's answer. A 180° answer
    is checked first: the check confidently flips upright pages that have
    dark areas around them, and a flipped page loses all its text. So read
    the page both ways (fast models) and keep the way Tesseract is surer of."""
    rotation = await detect_rotation(image_png)
    if not rotation:
        return image_png
    turned = await asyncio.to_thread(turn_upright, image_png, rotation)
    if rotation == 180:
        # ponytail: two extra fast reads (about 2x the time) for pages the
        # check calls upside down; reuse the winning read if that gets slow.
        as_is = mean_word_confidence(
            (await run_tesseract(image_png, "text", "tsv")).decode("utf-8", "replace"))
        flipped = mean_word_confidence(
            (await run_tesseract(turned, "text", "tsv")).decode("utf-8", "replace"))
        if flipped <= as_is:
            return image_png
    return turned


def to_jpeg_data_url(image_png: bytes) -> str:
    """The prepared page for display; JPEG keeps it a fraction of the PNG."""
    buf = io.BytesIO()
    Image.open(io.BytesIO(image_png)).convert("L").save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


async def run_tesseract(
    image_png: bytes, mode: str, renderer: Optional[str] = None, model: str = "fast"
) -> bytes:
    """Run the tesseract CLI on a PNG passed through stdin (no temp files, so
    patient documents never touch the disk)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            TESSERACT_CMD, "stdin", "stdout",
            *(["--tessdata-dir", TESSDATA_BEST_DIR] if model == "best" else []),
            "-l", TESSERACT_LANGS,
            "--psm", str(TESSERACT_PSM[mode]),
            "-c", "preserve_interword_spaces=1",
            # A setting, not the "tsv" config file: that file lives in the
            # default tessdata folder, which --tessdata-dir hides.
            *(["-c", f"tessedit_create_{renderer}=1"] if renderer else []),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=TESSERACT_ENV,
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


# Tokens a wrong character makes dangerous: dates, ICD-10 codes, dosages,
# other numbers. Tried in this order at each position, so a date isn't
# split into numbers. The bench scores them and the word check in
# static/index.html highlights them with the same parts (a test keeps the
# copies equal).
CRITICAL_PARTS = (
    r"\d{1,2}[./]\d{1,2}[./]\d{2,4}",  # dates
    r"[A-ZА-ЯІЇЄҐ]\d\d(?:\.\d+)?",  # ICD-10 codes
    r"\d+(?:,\d+)?\s?(?:мг|мл|г|од)",  # dosages
    r"\d+(?:[.,]\d+)?",  # other numbers
)
CRITICAL = re.compile(r"(?<!\w)(?:" + "|".join(CRITICAL_PARTS) + r")(?!\w)")

# Latin and Cyrillic letters that look the same, in matching order.
LATIN_LOOKALIKES = "aceiopxyïACEHIKMOPTXB"
CYRILLIC_LOOKALIKES = "асеіорхуїАСЕНІКМОРТХВ"
TO_CYRILLIC = str.maketrans(LATIN_LOOKALIKES, CYRILLIC_LOOKALIKES)
TO_LATIN = str.maketrans(CYRILLIC_LOOKALIKES, LATIN_LOOKALIKES)
# Letters read in place of digits: O/o (Latin and Cyrillic) = 0, З/з = 3, l/I/І/| = 1.
TO_DIGITS = str.maketrans("OoОоЗзlIІ|", "0000331111")
DIGIT_LOOKALIKES = "OoОоЗзlIІ|"
ICD10 = re.compile(r"([A-ZА-ЯІЇЄҐ])([0-9%s]{2})(\.[0-9%s]{1,2})?" % ((DIGIT_LOOKALIKES,) * 2))


def fix_word(word: str) -> str:
    """Repair one OCR word: an ICD-10 code gets a Latin letter and digits; a
    number or date gets digits for look-alike letters (only when real digits
    outnumber them, so "O2" and "CO2" stay); otherwise look-alike letters are
    switched to the script that the word's unambiguous letters are mostly
    in, or to Latin when there are none but there are digits (СO2 -> CO2)."""
    lead, core, tail = re.fullmatch(r"(\W*)(.*?)(\W*)", word).groups()
    digits = sum(c.isdigit() for c in core)

    lookalikes = sum(c in DIGIT_LOOKALIKES for c in core)
    icd = ICD10.fullmatch(core)
    if icd and digits > sum(c in DIGIT_LOOKALIKES for c in core[1:]):
        letter = icd.group(1).translate(TO_LATIN)
        if letter.isascii():
            return lead + letter + core[1:].translate(TO_DIGITS) + tail

    others = sum(c.isalpha() and c not in DIGIT_LOOKALIKES for c in core)
    if digits and not others and digits > lookalikes:
        return lead + core.translate(TO_DIGITS) + tail

    cyrillic = sum("\u0400" <= c <= "\u04ff" and c not in CYRILLIC_LOOKALIKES for c in core)
    latin = sum(c.isalpha() and c.isascii() and c not in LATIN_LOOKALIKES for c in core)
    # No unambiguous letters but digits (CO2, B12 with a Cyrillic С or В):
    # formulas and codes are written in Latin.
    if cyrillic > latin:
        core = core.translate(TO_CYRILLIC)
    elif latin > cyrillic or digits:
        core = core.translate(TO_LATIN)
    return lead + core + tail


# An ICD-10 code anywhere in the text, also glued to other characters
# ("2,0м(Н90.3)") and with a space after the dot ("H66. 1"). ICD-10 letters
# are Latin; the Cyrillic look-alikes are mapped below.
ICD10_IN_TEXT = re.compile(r"(?<!\w)([A-ZАВЕКМНОРСТХІ])(\d\d)(?:\.( ?)(\d{1,2}))?(?!\w|\. ?\d)")


def fix_icd10(text: str) -> str:
    """Latin letter for ICD-10 codes (Н66.1 -> H66.1) and no space after the
    dot (X00. 1 -> X00.1). Only tokens that are a whole code change."""
    def fix(m):
        letter, number, _, decimals = m.groups()
        return letter.translate(TO_LATIN) + number + ("." + decimals if decimals else "")
    return ICD10_IN_TEXT.sub(fix, text)


def postprocess_text(text: str) -> str:
    # ICD-10 last: fix_word turns a mostly Cyrillic word's look-alikes Cyrillic,
    # which would undo the code's Latin letter in "Н66.1)Хронічна".
    return fix_icd10(re.sub(r"\S+", lambda m: fix_word(m.group()), text))


def postprocess_tsv(tsv: str) -> str:
    """fix_word and fix_icd10 on the text column of each word row; boxes and
    confidences stay. Codes split over two words ("H66." "1") stay split."""
    rows = tsv.split("\n")
    for i, row in enumerate(rows):
        cells = row.split("\t")
        if len(cells) == 12 and cells[0] == "5":
            cells[11] = fix_icd10(fix_word(cells[11]))
            rows[i] = "\t".join(cells)
    return "\n".join(rows)


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


async def cancel_on_disconnect(request: Request, coro):
    """Run an OCR coroutine, cancelling it once the browser disconnects (the
    UI's Stop button) so tesseract doesn't keep burning CPU."""
    task = asyncio.ensure_future(coro)
    while True:
        done, _ = await asyncio.wait({task}, timeout=1)
        if done:
            return task.result()
        if await request.is_disconnected():
            task.cancel()  # kills tesseract
            await asyncio.gather(task, return_exceptions=True)
            raise HTTPException(status_code=499, detail="Запит скасовано клієнтом")



# --- Endpoints --------------------------------------------------------------

@app.get("/health")
async def health():
    tesseract = await tesseract_status()
    if not tesseract["available"]:
        return JSONResponse(
            status_code=503, content={"status": "tesseract_unavailable", "tesseract": tesseract}
        )
    return {"status": "ok", "tesseract": tesseract}


@app.post("/ocr")
async def ocr(
    request: Request,
    file: UploadFile = File(...),
    mode: Literal["text", "table", "block"] = Form("text"),
    output: Literal["text", "json", "tsv", "words"] = Form("json"),
    max_megapixels: Optional[float] = Form(None),
    model: Literal["fast", "best"] = Form("fast"),
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

    if model == "best" and not os.path.isdir(TESSDATA_BEST_DIR):
        raise HTTPException(
            status_code=503,
            detail=f"Точні моделі не встановлено на сервері. Деталі: немає {TESSDATA_BEST_DIR}",
        )

    renderer = "tsv" if output in ("tsv", "words") else None
    started = time.time()
    out, page_png = await cancel_on_disconnect(
        request,
        tesseract_ocr(raw, mode, max_megapixels or TESSERACT_MAX_MEGAPIXELS, renderer, model),
    )
    result = out.decode("utf-8", errors="replace")
    if POSTPROCESS:
        result = postprocess_tsv(result) if renderer else postprocess_text(result)
    if output == "words":
        # TSV word boxes are in the prepared page's pixels, so the page
        # comes along: the UI shows it and draws boxes on it as-is.
        return JSONResponse({
            "tsv": result,
            "image": await asyncio.to_thread(to_jpeg_data_url, page_png),
            "seconds": round(time.time() - started, 2),
        })
    if output == "tsv":
        return PlainTextResponse(
            result,
            media_type="text/tab-separated-values",
        )

    text = clean_tesseract_text(result)
    if output == "text":
        return PlainTextResponse(text)
    return {
        "text": text,
        "mode": mode,
        "model": f"tesseract {model} ({TESSERACT_LANGS})",
        "seconds": round(time.time() - started, 2),
        "filename": file.filename,
    }


@app.get("/api")
async def api_info():
    return {
        "service": "ocr-service",
        "endpoints": {
            "GET /": "web interface — upload an image, get copiable text",
            "POST /ocr": "multipart form: file, mode=text|table|block, output=json|text|tsv|words, max_megapixels, model=fast|best",
            "GET /health": "checks that Tesseract runs and has every language in TESSERACT_LANGS",
        },
    }


@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
