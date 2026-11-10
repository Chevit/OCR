"""Experiment: RapidOCR (onnxruntime) with PP-OCRv5 detection and the East
Slavic (eslav) recognizer from monkt/paddleocr-onnx, on the same prepared
page Tesseract gets. Bench only; the service doesn't use it.

    docker compose run --build --rm bench python -m tests.bench.bench Examples \
        --preprocess v2 --psm 3 --dpi 0 --thresh 0 --model fast,best,rapidocr --jobs 4

Runs fully offline. The bench image has the model files baked in
(Dockerfile, pinned by SHA-256) and no network. Outside Docker, put them in
tests/bench/models/ (git-ignored) or point RAPIDOCR_MODELS_DIR at them; the
hashes are checked before use. RapidOCR gets explicit paths for every file
and its downloader is blocked, so a missing file fails instead of fetching.

Each parallel job is its own process with one onnxruntime thread (like
Tesseract's OMP_THREAD_LIMIT=1), so its peak RAM is measured on its own.
"""
import hashlib
import multiprocessing
import os
import resource
import sys
import time
from concurrent.futures import ProcessPoolExecutor

MODELS_DIR = os.environ.get(
    "RAPIDOCR_MODELS_DIR", os.path.join(os.path.dirname(__file__), "models"))
# monkt/paddleocr-onnx at commit 7b02d0a30a07ba2b92ad1ff5a8941ae2c633de65;
# same files and hashes as the Dockerfile's bench stage. The repo has only
# the server-size detector for PP-OCRv5 (88 MB).
MODELS = {
    "det.onnx": "61824840edf6e74581898930b8091b1b2318f4b2705a2e8a40ad3de7ac480133",  # detection/v5
    "rec.onnx": "dc6bf0e855247decce214ba6dae5bc135fa0ad725a5918a7fcfb59fad6c9cdee",  # languages/eslav
    "dict.txt": "3e95f1581557162870cacdba5af91a4c6be2890710d395b0c3c7578e7ee5e6eb",  # languages/eslav
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_models():
    for name, digest in MODELS.items():
        path = os.path.join(MODELS_DIR, name)
        if not os.path.exists(path):
            sys.exit(f"{path} missing; run the bench in Docker (models are in the image)")
        if sha256(path) != digest:
            sys.exit(f"{path}: SHA-256 mismatch")


_engine = None


def _init():
    global _engine
    from rapidocr import RapidOCR
    from rapidocr.utils.download_file import DownloadFile

    def offline(cls, params):
        raise RuntimeError(f"RapidOCR tried to download {params.file_url}; the bench is offline")

    # Every module that fetches files calls this one class method.
    DownloadFile.run = classmethod(offline)
    import onnxruntime
    onnxruntime.disable_telemetry_events()  # Windows-only events; off anyway
    m = lambda name: os.path.join(MODELS_DIR, name)
    _engine = RapidOCR(params={
        "Global.model_root_dir": MODELS_DIR,  # where any default lookup would land
        "Global.use_cls": False,  # the page is already upright
        "Global.log_level": "error",
        "EngineConfig.onnxruntime.intra_op_num_threads": 1,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "Det.model_path": m("det.onnx"),
        "Rec.model_path": m("rec.onnx"),
        "Rec.rec_keys_path": m("dict.txt"),
    })


def _read(png):
    started = time.perf_counter()
    out = _engine(png)
    seconds = time.perf_counter() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss *= 1 if sys.platform == "darwin" else 1024  # bytes on macOS, KiB on Linux
    return "\n".join(out.txts or ()), seconds, rss


_pool = None


def read(png, jobs):
    """Text of a prepared page, seconds, and the peak RSS of the job's process."""
    global _pool
    if _pool is None:
        check_models()
        # spawn, not fork: the bench's threads are running (fork is Linux's default).
        _pool = ProcessPoolExecutor(jobs, multiprocessing.get_context("spawn"), initializer=_init)
    return _pool.submit(_read, png).result()
