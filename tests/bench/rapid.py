"""Experiment: RapidOCR (onnxruntime) with PP-OCRv5 detection and the East
Slavic (eslav) recognizer from monkt/paddleocr-onnx, on the same prepared
page Tesseract gets. Bench only; the service doesn't use it.

    docker compose run --build --rm bench python -m tests.bench.bench Examples \
        --preprocess v2 --psm 3 --dpi 0 --thresh 0 --model fast,best,rapidocr --jobs 4

"rapidocr-v5-mobile", "rapidocr-v6-tiny" and "rapidocr-v6-small" swap in
the official PaddlePaddle ONNX detectors with their own settings
(DETECTORS); the recognizer stays eslav PP-OCRv5 mobile.

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
import threading
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
    # Official PaddlePaddle ONNX detectors on Hugging Face (inference.onnx of
    # PaddlePaddle/<repo> at the commit in the Dockerfile).
    "det_v5_mobile.onnx": "a431985659dc921974177a95adcfbb90fd9e51989a5e04d70d0b75f597b6e61d",
    "det_v6_tiny.onnx": "193bab7a04fca699a6c82e6abb5b81bdb28177f0abd4062552b04908dafb19f8",
    "det_v6_small.onnx": "d73e0058b7a8086bbd57f3d10b8bcd4ff95363f67e06e2762b5e814fe9c9410e",
}

# Detector settings of the official models: each repo's inference.yml plus
# PaddleX 3.7.2's text_detection predictor for what that file leaves out. The
# v5 file says resize_long 960; v6 has no resize settings, so the predictor's
# default for these models applies (longest side <= 960). ImageNet
# normalization; DB post-processing without dilation (PaddleX default).
# ponytail: Global.max_side_len stays RapidOCR's 2000 for every variant, so
# all of them crop the recognizer's lines from the same image.
_OFFICIAL = {"Det.limit_side_len": 960, "Det.limit_type": "max",
             "Det.mean": [0.485, 0.456, 0.406], "Det.std": [0.229, 0.224, 0.225],
             "Det.use_dilation": False, "Det.score_mode": "fast"}
_DB = lambda thresh, box, unclip, cand: {"Det.thresh": thresh, "Det.box_thresh": box,
                                         "Det.unclip_ratio": unclip, "Det.max_candidates": cand}
# Bench model name -> detector file and settings; all use the eslav recognizer.
DETECTORS = {
    "rapidocr": ("det.onnx", {}),  # RapidOCR's defaults, as in RESULTS.md (4)
    "rapidocr-v5-mobile": ("det_v5_mobile.onnx", {**_OFFICIAL, **_DB(0.3, 0.6, 1.5, 1000)}),
    "rapidocr-v6-tiny": ("det_v6_tiny.onnx", {**_OFFICIAL, **_DB(0.2, 0.4, 1.4, 3000)}),
    "rapidocr-v6-small": ("det_v6_small.onnx", {**_OFFICIAL, **_DB(0.2, 0.45, 1.4, 3000)}),
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


def _init(model):
    det, det_params = DETECTORS[model]
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
        "Det.model_path": m(det),
        "Rec.model_path": m("rec.onnx"),
        "Rec.rec_keys_path": m("dict.txt"),
        **det_params,
    })


def _read(png):
    started = time.perf_counter()
    out = _engine(png)
    seconds = time.perf_counter() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss *= 1 if sys.platform == "darwin" else 1024  # bytes on macOS, KiB on Linux
    return "\n".join(out.txts or ()), seconds, rss


_pools = {}  # bench model name -> its process pool
_pool_lock = threading.Lock()  # the bench calls read() from several threads at once


def read(png, jobs, model="rapidocr"):
    """Text of a prepared page, seconds, and the peak RSS of the job's process."""
    with _pool_lock:
        if model not in _pools:
            check_models()
            # Variants run in order: free the last model's processes
            # first, or every RapidOCR variant would hold its RAM to the end.
            for pool in _pools.values():
                pool.shutdown()
            _pools.clear()
            # spawn, not fork: the bench's threads are running (fork is Linux's default).
            _pools[model] = ProcessPoolExecutor(jobs, multiprocessing.get_context("spawn"),
                                                initializer=_init, initargs=(model,))
        job = _pools[model].submit(_read, png)  # under the lock: a pool may be shut down next
    return job.result()
