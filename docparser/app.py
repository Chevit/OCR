"""Thin FastAPI wrapper around PaddleOCR's own PaddleOCRVL pipeline —
the "official" doc-parsing path, as opposed to the single-prompt VLM call
the main `ocr` service makes to Ollama.

Unlike the Ollama route, this actually runs layout detection
(PP-DocLayoutV2) to find where headings/paragraphs/tables/images sit on
the page, then recognizes each region individually and reassembles the
result as Markdown in reading order. That's slower and only runs on
amd64 (see the Dockerfile), but the structure it produces is genuinely
derived from the page layout rather than guessed in one pass.
"""
import os
import tempfile
import threading
import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

app = FastAPI(title="glm-ocr-docparser", version="1.0.0")

_pipeline = None
_pipeline_lock = threading.Lock()


def get_pipeline():
    """Built lazily on first request rather than at import time.

    Importing `paddleocr` pulls in paddlepaddle, and constructing
    PaddleOCRVL triggers a multi-GB model download on the very first
    call ever made against this container (cached afterwards in the
    /root/.paddlex volume, so later requests skip straight to loading
    weights). The download pulls from several mirrors in turn (Baidu's
    AIStudio, then ModelScope, then BOS) and falls through to the next
    one on failure — from outside China, the first two often fail to
    resolve at all and it lands on BOS, which alone can take several
    minutes.

    The lock guards against a second request racing in while the first
    is still constructing the pipeline (this function runs in a
    threadpool — see _run_parse below — so that's a real possibility,
    not just a formality): without it, two concurrent callers could both
    see _pipeline as None and both start their own PaddleOCRVL(), doubly
    downloading and initializing at once.
    """
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:  # re-check: another thread may have won the race
                from paddleocr import PaddleOCRVL

                _pipeline = PaddleOCRVL(device="cpu")
    return _pipeline


def _run_parse(raw: bytes, filename: str) -> tuple[str, float]:
    """Everything CPU-bound and blocking — loading the pipeline (including
    the first-run model download) and running inference — happens here,
    off the event loop (see the /parse handler, which runs this in a
    worker thread). Without that, a slow first request would freeze the
    whole server, including /health, instead of just taking a while."""
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, filename or "input.png")
        with open(in_path, "wb") as f:
            f.write(raw)

        pipeline = get_pipeline()

        started = time.time()
        output = list(pipeline.predict(input=in_path))
        elapsed = round(time.time() - started, 2)

        if not output:
            raise RuntimeError("Pipeline returned no result")

        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir, exist_ok=True)
        for res in output:
            res.save_to_markdown(save_path=out_dir)

        # One .md file per detected page — a single-image request only
        # ever produces one, but this handles multi-page input the same
        # way in case /parse is ever pointed at a PDF.
        markdown_parts = []
        for name in sorted(os.listdir(out_dir)):
            if name.endswith(".md"):
                with open(os.path.join(out_dir, name), "r", encoding="utf-8") as f:
                    markdown_parts.append(f.read())

        if not markdown_parts:
            raise RuntimeError("Pipeline produced no Markdown output")

        return "\n\n".join(markdown_parts), elapsed


@app.get("/health")
async def health():
    # Stays responsive even while a slow first request is still loading
    # the pipeline or downloading models in its own worker thread, since
    # that work no longer runs on the event loop.
    return {"status": "ok", "pipeline_loaded": _pipeline is not None}


@app.post("/parse")
async def parse(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file upload")

    try:
        markdown, elapsed = await run_in_threadpool(_run_parse, raw, file.filename)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"PaddleOCR-VL pipeline error: {exc}"
        )

    return JSONResponse({"markdown": markdown, "seconds": elapsed})
