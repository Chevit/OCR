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
import collections
import itertools
import os
import platform
import re
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


# Tokens a wrong character makes dangerous: dates, ICD-10 codes, dosages,
# other numbers. Tried in this order at each position, so a date isn't
# split into numbers.
CRITICAL = re.compile(
    r"(?<!\w)(?:"
    r"\d{1,2}[./]\d{1,2}[./]\d{2,4}"  # dates
    r"|[A-ZА-ЯІЇЄҐ]\d\d(?:\.\d+)?"  # ICD-10 codes
    r"|\d+(?:,\d+)?\s?(?:мг|мл|г|од)"  # dosages
    r"|\d+(?:[.,]\d+)?"  # other numbers
    r")(?!\w)"
)


def bag(pattern, text, normalize=str.lower):
    return collections.Counter(normalize(m) for m in re.findall(pattern, text))


def score(truth, text):
    """Counts for one page, summed over pages for pooled rates. Whitespace is
    collapsed first. Word recall/precision ignore order: a page read in
    another block order (stamp before header) has bad CER yet every word."""
    t, h = " ".join(truth.split()), " ".join(text.split())
    words_t, words_h = bag(r"\w+", t), bag(r"\w+", h)
    no_space = lambda m: "".join(m.split())
    crit_t, crit_h = bag(CRITICAL, t, no_space), bag(CRITICAL, h, no_space)
    return collections.Counter(
        char_errors=Levenshtein.distance(t, h), chars=len(t),
        word_errors=Levenshtein.distance(t.split(), h.split()), words=len(t.split()),
        words_found=sum((words_t & words_h).values()),
        words_truth=sum(words_t.values()), words_output=sum(words_h.values()),
        critical_found=sum((crit_t & crit_h).values()), critical_truth=sum(crit_t.values()),
    )


def run(samples, variants, jobs):
    """variant -> [(sample name, score, seconds, score with POSTPROCESS=1)]"""
    with ThreadPoolExecutor(jobs) as pool:
        keys = sorted({(v[0], i) for v in variants for i in range(len(samples))})
        prepared = dict(zip(keys, pool.map(lambda k: prepare(samples[k[1]][1], k[0]), keys)))
        tasks = [(v, i) for v in variants for i in range(len(samples))]
        outputs = pool.map(lambda t: tesseract(prepared[t[0][0], t[1]][0], *t[0][1:]), tasks)
        results = {}
        for (v, i), (text, seconds) in zip(tasks, outputs):
            name, _, truth = samples[i]
            results.setdefault(v, []).append((name, score(truth, text), seconds + prepared[v[0], i][1],
                                              score(truth, app.postprocess_text(text))))
    return results


def label(variant):
    preprocess, psm, dpi, thresholding, model = variant
    return f"{preprocess}, psm {psm}, dpi {dpi or '-'}, thresh {thresholding}, {model}"


def cer(s):
    return s["char_errors"] / s["chars"]


def rates(s):
    """Rates from (summed) counts: CER, WER, word recall/precision/F1, critical tokens."""
    recall = s["words_found"] / s["words_truth"]
    precision = s["words_found"] / s["words_output"] if s["words_output"] else 0.0
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
    critical = s["critical_found"] / s["critical_truth"] if s["critical_truth"] else 1.0
    return cer(s), s["word_errors"] / s["words"], recall, precision, f1, critical


COLUMNS = ("CER pooled", "CER mean", "CER median", "WER", "Word recall", "Word precision",
           "Word F1", "Critical tokens", "Critical, POSTPROCESS=1", "CER, POSTPROCESS=1")


def summary(rows):
    """One table row's numbers: pooled rates, plus the mean and median of
    per-image CER (one bad image moves the pooled number, the median barely)."""
    total = sum((r[1] for r in rows), collections.Counter())
    post = sum((r[3] for r in rows), collections.Counter())
    pooled_cer, wer, recall, precision, f1, critical = rates(total)
    per_image = [cer(r[1]) for r in rows]
    return (pooled_cer, statistics.mean(per_image), statistics.median(per_image), wer,
            recall, precision, f1, critical, rates(post)[5], cer(post),
            sum(r[2] for r in rows) / len(rows))


def table(named_rows, mark=None):
    """Markdown table of summary() rows, ranked by pooled CER."""
    print("| Variant | " + " | ".join(COLUMNS) + " | s/image |")
    print("|" + " --- |" * (len(COLUMNS) + 2))
    for name, rows in sorted(named_rows.items(), key=lambda kv: summary(kv[1])[0]):
        *pct, seconds = summary(rows)
        tag = " (service default)" if name == mark else ""
        print(f"| {name}{tag} | " + " | ".join(f"{x:.1%}" for x in pct) + f" | {seconds:.1f} |")


def report(results, default):
    table({label(v): rows for v, rows in results.items()}, mark=label(default))

    # Per image, the service's default settings against the overall winner.
    best = min(results, key=lambda v: summary(results[v])[0])
    cols = [default, best] if default in results and best != default else [best]
    print("\n| Image | " + " | ".join(f"{label(v)}: CER / recall / critical" for v in cols) + " |")
    print("| --- |" + " --- |" * len(cols))
    for i, (name, *_rest) in enumerate(results[best]):
        cells = []
        for v in cols:
            c, _, recall, _, _, critical = rates(results[v][i][1])
            cells.append(f"{c:.1%} / {recall:.0%} / {critical:.0%}")
        print(f"| {name} | " + " | ".join(cells) + " |")


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
    report(run(samples, variants, a.jobs), default=(app.PREPROCESS, 3, 0, 0, "fast"))


if __name__ == "__main__":
    main()
