"""Recognition benchmark: character and word error rates (CER, WER) and
seconds per image for each Tesseract variant, on images with hand-typed
ground truth (name.png|jpg|jpeg|webp next to name.gt.txt). See README.md.

    pip install -r tests/bench/requirements.txt
    python -m tests.bench.bench                     # Examples/
    python -m tests.bench.bench Examples/holdout --psm 4 --model fast

Images go through the service's own preparation (prepare_for_tesseract and
make_upright), then every combination of the variant options runs.
Whitespace and line breaks are collapsed before comparing: layout is not
scored, only the characters and words.
"""
import argparse
import asyncio
import itertools
import os
import platform
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from rapidfuzz.distance import Levenshtein

from app import main as app

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def load_samples(dirs):
    samples = []
    for d in dirs:
        for name in sorted(os.listdir(d)):
            stem, ext = os.path.splitext(name)
            gt = os.path.join(d, stem + ".gt.txt")
            if ext.lower() in IMAGE_EXTS and os.path.exists(gt):
                with open(os.path.join(d, name), "rb") as f, open(gt, encoding="utf-8") as g:
                    samples.append((stem, f.read(), g.read()))
    if not samples:
        sys.exit(f"no image + .gt.txt pairs in {dirs}")
    return samples


def prepare(raw, preprocess):
    """The service's preparation; returns the PNG Tesseract reads and the seconds it took."""
    started = time.perf_counter()
    png = app.prepare_for_tesseract(raw, app.TESSERACT_MAX_MEGAPIXELS, preprocess)
    png = asyncio.run(app.make_upright(png))
    return png, time.perf_counter() - started


def tesseract(png, psm, dpi, thresholding, model):
    cmd = [
        app.TESSERACT_CMD, "stdin", "stdout",
        *(["--tessdata-dir", app.TESSDATA_BEST_DIR] if model == "best" else []),
        "-l", app.TESSERACT_LANGS, "--psm", str(psm),
        *(["--dpi", str(dpi)] if dpi else []),
        "-c", "preserve_interword_spaces=1",
        "-c", f"thresholding_method={thresholding}",
    ]
    started = time.perf_counter()
    out = subprocess.run(cmd, input=png, capture_output=True, env=app.TESSERACT_ENV, check=True)
    return out.stdout.decode("utf-8", errors="replace"), time.perf_counter() - started


def errors(truth, text):
    """(char errors, chars, word errors, words) after collapsing whitespace."""
    t, h = " ".join(truth.split()), " ".join(text.split())
    return (Levenshtein.distance(t, h), len(t),
            Levenshtein.distance(t.split(), h.split()), len(t.split()))


def run(samples, variants, jobs):
    with ThreadPoolExecutor(jobs) as pool:
        keys = sorted({(v[0], i) for v in variants for i in range(len(samples))})
        prepared = dict(zip(keys, pool.map(lambda k: prepare(samples[k[1]][1], k[0]), keys)))
        tasks = [(v, i) for v in variants for i in range(len(samples))]
        outputs = pool.map(lambda t: tesseract(prepared[t[0][0], t[1]][0], *t[0][1:]), tasks)
        results = {}  # variant -> list of (sample name, errors, seconds)
        for (v, i), (text, seconds) in zip(tasks, outputs):
            name, _, truth = samples[i]
            results.setdefault(v, []).append((name, errors(truth, text), seconds + prepared[v[0], i][1]))
    return results


def label(variant):
    preprocess, psm, dpi, thresholding, model = variant
    return f"{preprocess}, psm {psm}, dpi {dpi or '-'}, thresh {thresholding}, {model}"


def cer(row):
    return row[1][0] / row[1][1]


def report(results, baseline):
    """Variants ranked by pooled CER (all errors / all characters), with the
    mean and median of per-image CER beside it: one bad image moves the
    pooled number a lot, the median barely."""
    def totals(rows):
        ce, c, we, w = (sum(r[1][k] for r in rows) for k in range(4))
        per_image = [cer(r) for r in rows]
        return (ce / c, statistics.mean(per_image), statistics.median(per_image),
                we / w, sum(r[2] for r in rows) / len(rows))

    print("| Variant | CER pooled | CER mean | CER median | WER pooled | s/image |")
    print("| --- | --- | --- | --- | --- | --- |")
    ranked = sorted(results, key=lambda v: totals(results[v])[0])
    for v in ranked:
        mark = " (baseline)" if v == baseline else ""
        cells = " | ".join(f"{x:.1%}" for x in totals(results[v])[:4])
        print(f"| {label(v)}{mark} | {cells} | {totals(results[v])[4]:.1f} |")

    # Per image, the current service settings against the overall winner.
    best = ranked[0]
    cols = [baseline, best] if baseline in results and best != baseline else [best]
    print("\n| Image | " + " | ".join(f"CER {label(v)}" for v in cols) + " |")
    print("| --- |" + " --- |" * len(cols))
    for i, (name, *_rest) in enumerate(results[best]):
        print(f"| {name} | " + " | ".join(f"{cer(results[v][i]):.1%}" for v in cols) + " |")


def machine():
    """Timings only compare on the same machine; the Pi is the one that counts."""
    try:
        with open("/proc/device-tree/model") as f:  # Raspberry Pi
            return f.read().strip("\0\n")
    except OSError:
        pass
    try:
        return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],  # macOS
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return platform.machine()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("dirs", nargs="*", default=["Examples"],
                   help="folders with images and .gt.txt files (subfolders are not read)")
    p.add_argument("--preprocess", default="baseline,v2")
    p.add_argument("--psm", default="3,4,6")
    p.add_argument("--dpi", default="0,300", help="0 = don't pass --dpi")
    p.add_argument("--thresh", default="0,2", help="thresholding_method: 0 Otsu, 2 Sauvola")
    p.add_argument("--model", default="fast,best")
    p.add_argument("--jobs", type=int, default=os.cpu_count(),
                   help="parallel tesseract runs; 1 gives the cleanest timings")
    a = p.parse_args()

    split = lambda s, f=str: [f(x) for x in s.split(",")]
    variants = list(itertools.product(split(a.preprocess), split(a.psm, int), split(a.dpi, int),
                                      split(a.thresh, int), split(a.model)))
    if "best" in split(a.model) and not os.path.isdir(app.TESSDATA_BEST_DIR):
        sys.exit(f"model best needs {app.TESSDATA_BEST_DIR} (set TESSDATA_BEST_DIR)")
    samples = load_samples(a.dirs)
    print(f"{len(samples)} images, {len(variants)} variants; "
          f"timings on {machine()}, {a.jobs} parallel jobs\n")
    report(run(samples, variants, a.jobs), baseline=("baseline", 3, 0, 0, "fast"))


if __name__ == "__main__":
    main()
