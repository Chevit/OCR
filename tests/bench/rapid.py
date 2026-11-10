"""Experiment: RapidOCR (onnxruntime) with PP-OCRv5 detection and the East
Slavic (eslav) recognizer from monkt/paddleocr-onnx, on the same prepared
page Tesseract gets. Bench only; the service doesn't use it.

    pip install -r tests/bench/requirements-rapidocr.txt
    python -m tests.bench.bench Examples --preprocess v2 --psm 3 --dpi 0 --thresh 0 \
        --model fast,best,rapidocr --jobs 4

Model files are downloaded once into tests/bench/models/ (git-ignored) from
a pinned commit and checked by SHA-256. Each parallel job is its own process
with one onnxruntime thread (like Tesseract's OMP_THREAD_LIMIT=1), so its
peak RAM is measured on its own.
"""
import hashlib
import multiprocessing
import os
import resource
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
BASE = ("https://huggingface.co/monkt/paddleocr-onnx/resolve/"
        "7b02d0a30a07ba2b92ad1ff5a8941ae2c633de65/")
# The repo has only the server-size detector for PP-OCRv5 (88 MB).
MODELS = {
    "det.onnx": ("detection/v5/det.onnx",
                 "61824840edf6e74581898930b8091b1b2318f4b2705a2e8a40ad3de7ac480133"),
    "rec.onnx": ("languages/eslav/rec.onnx",
                 "dc6bf0e855247decce214ba6dae5bc135fa0ad725a5918a7fcfb59fad6c9cdee"),
    "dict.txt": ("languages/eslav/dict.txt",
                 "3e95f1581557162870cacdba5af91a4c6be2890710d395b0c3c7578e7ee5e6eb"),
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_models():
    """Download missing model files; refuse any file whose hash differs."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    for name, (remote, digest) in MODELS.items():
        path = os.path.join(MODELS_DIR, name)
        if not os.path.exists(path):
            urllib.request.urlretrieve(BASE + remote, path + ".part")
            os.replace(path + ".part", path)
        if sha256(path) != digest:
            os.remove(path)
            sys.exit(f"{name}: SHA-256 mismatch, file removed")


_engine = None


def _init():
    global _engine
    from rapidocr import RapidOCR

    m = lambda name: os.path.join(MODELS_DIR, name)
    _engine = RapidOCR(params={
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
        fetch_models()
        # spawn, not fork: the bench's threads are running (fork is Linux's default).
        _pool = ProcessPoolExecutor(jobs, multiprocessing.get_context("spawn"), initializer=_init)
    return _pool.submit(_read, png).result()
