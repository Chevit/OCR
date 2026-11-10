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
import bisect
import collections
import itertools
import os
import platform
import re
import statistics
import subprocess
import sys
import threading
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


def prepare(raw):
    """The service's preparation; returns the PNG Tesseract reads and the seconds it took."""
    started = time.perf_counter()
    png = app.prepare_for_tesseract(raw, app.TESSERACT_MAX_MEGAPIXELS)
    png = asyncio.run(app.make_upright(png))
    return png, time.perf_counter() - started


# The old preparation (sized by megapixels, no lighting fix), removed from
# the service; its last numbers on Examples/ for comparison (RESULTS.md (14)).
BASELINE = ("Last recorded baseline preparation, Examples/, psm 3, fast: CER 34.0%, "
            "word recall 70.2%, word F1 71.4%, critical (positional) 61.8%, "
            "2+ chars 67.4%, POSTPROCESS=1 62.3%")


# Peak RSS (bytes) of one job, per model: what one parallel run needs.
PEAK_RSS = collections.defaultdict(int)
JOBS = 1


def tesseract(png, psm, dpi, thresholding, model, tsv=False):
    if model.startswith("rapidocr"):  # experiment, see rapid.py; psm/dpi/thresh don't apply
        from tests.bench import rapid
        text, seconds, rss = rapid.read(png, JOBS, model)
        PEAK_RSS[model] = max(PEAK_RSS[model], rss)
        return text, seconds
    cmd = [
        app.TESSERACT_CMD, "stdin", "stdout",
        *(["--tessdata-dir", app.TESSDATA_BEST_DIR] if model == "best" else []),
        "-l", app.TESSERACT_LANGS, "--psm", str(psm),
        *(["--dpi", str(dpi)] if dpi else []),
        "-c", "preserve_interword_spaces=1",
        "-c", f"thresholding_method={thresholding}",
        *(["-c", "tessedit_create_tsv=1"] if tsv else []),
    ]
    started = time.perf_counter()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, env=app.TESSERACT_ENV)
    out = []
    reader = threading.Thread(target=lambda: out.append(proc.stdout.read()))
    reader.start()
    proc.stdin.write(png)
    proc.stdin.close()
    reader.join()
    # wait4 instead of wait: it also returns the child's peak RSS.
    _, status, usage = os.wait4(proc.pid, 0)
    proc.returncode = os.waitstatus_to_exitcode(status)
    seconds = time.perf_counter() - started
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    rss = usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024)  # bytes / KiB
    PEAK_RSS[model] = max(PEAK_RSS[model], rss)
    return out[0].decode("utf-8", errors="replace"), seconds


CRITICAL = app.CRITICAL  # dates, ICD-10 codes, dosages, numbers


def bag(pattern, text, normalize=str.lower):
    return collections.Counter(normalize(m) for m in re.findall(pattern, text))


def no_space(m):
    return "".join(m.split())


def critical_read(t, h):
    """Positional critical tokens: (found, truth, found 2+ chars, truth 2+ chars).
    Output words are aligned to ground-truth words (Levenshtein on word
    sequences); a ground-truth token counts as read only if the output words
    aligned to it contain exactly that token. A correct date elsewhere on the
    page doesn't count, unlike the old order-free count."""
    tw, hw = t.split(), h.split()
    aligned = {}  # truth word index -> output word indices
    for tag, i1, i2, j1, j2 in Levenshtein.opcodes(tw, hw):
        if tag in ("equal", "replace"):
            m, n = i2 - i1, j2 - j1
            for i in range(i1, i2):  # spread a block proportionally (3 words read as 1, ...)
                lo = j1 + (i - i1) * n // m
                aligned[i] = range(lo, max(lo + 1, j1 + (i - i1 + 1) * n // m))
    starts = list(itertools.accumulate((len(w) + 1 for w in tw[:-1]), initial=0))
    counts = [0, 0, 0, 0]
    for match in re.finditer(CRITICAL, t):
        token = no_space(match.group())
        first = bisect.bisect_right(starts, match.start()) - 1
        last = bisect.bisect_right(starts, match.end() - 1) - 1
        js = sorted({j for i in range(first, last + 1) for j in aligned.get(i, ())})
        read = bool(js) and js == list(range(js[0], js[-1] + 1)) and token in {
            no_space(x) for x in re.findall(CRITICAL, " ".join(hw[js[0]:js[-1] + 1]))}
        counts[0] += read
        counts[1] += 1
        if len(token) >= 2:
            counts[2] += read
            counts[3] += 1
    return counts


def score(truth, text):
    """Counts for one page, summed over pages for pooled rates. Whitespace is
    collapsed first. Word recall/precision ignore order: a page read in
    another block order (stamp before header) has bad CER yet every word."""
    t, h = " ".join(truth.split()), " ".join(text.split())
    words_t, words_h = bag(r"\w+", t), bag(r"\w+", h)
    crit_t, crit_h = bag(CRITICAL, t, no_space), bag(CRITICAL, h, no_space)
    found, truth_n, found2, truth2 = critical_read(t, h)
    return collections.Counter(
        char_errors=Levenshtein.distance(t, h), chars=len(t),
        word_errors=Levenshtein.distance(t.split(), h.split()), words=len(t.split()),
        words_found=sum((words_t & words_h).values()),
        words_truth=sum(words_t.values()), words_output=sum(words_h.values()),
        critical_found=found, critical_truth=truth_n,
        critical2_found=found2, critical2_truth=truth2,
        # Deprecated order-free count, kept for one report for continuity.
        critical_bag_found=sum((crit_t & crit_h).values()), critical_bag_truth=sum(crit_t.values()),
    )


def run(samples, variants, jobs):
    """variant -> [(sample name, score, seconds, score with POSTPROCESS=1)]"""
    with ThreadPoolExecutor(jobs) as pool:
        prepared = list(pool.map(lambda smp: prepare(smp[1]), samples))
        tasks = [(v, i) for v in variants for i in range(len(samples))]
        outputs = pool.map(lambda t: tesseract(prepared[t[1]][0], *t[0]), tasks)
        results = {}
        for (v, i), (text, seconds) in zip(tasks, outputs):
            name, _, truth = samples[i]
            results.setdefault(v, []).append((name, score(truth, text), seconds + prepared[i][1],
                                              score(truth, app.postprocess_text(text))))
    return results


def label(variant):
    psm, dpi, thresholding, model = variant
    if model == "rapidocr":
        return "rapidocr (PP-OCRv5 det + eslav rec)"
    if model.startswith("rapidocr-"):
        det = model.removeprefix("rapidocr-").replace("-", " ")
        return f"rapidocr (PP-OCR{det} det + eslav rec)"
    return f"psm {psm}, dpi {dpi or '-'}, thresh {thresholding}, {model}"


def cer(s):
    return s["char_errors"] / s["chars"]


def rates(s):
    """Rates from (summed) counts: CER, WER, word recall/precision/F1, critical tokens."""
    recall = s["words_found"] / s["words_truth"]
    precision = s["words_found"] / s["words_output"] if s["words_output"] else 0.0
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
    critical = share(s, "critical")
    return cer(s), s["word_errors"] / s["words"], recall, precision, f1, critical


def share(s, name):
    return s[f"{name}_found"] / s[f"{name}_truth"] if s[f"{name}_truth"] else 1.0


COLUMNS = ("CER pooled", "CER mean", "CER median", "WER", "Word recall", "Word precision",
           "Word F1", "Critical (positional)", "Critical, 2+ chars", "Critical (order-free, deprecated)",
           "Critical, POSTPROCESS=1", "CER, POSTPROCESS=1")


def summary(rows):
    """One table row's numbers: pooled rates, plus the mean and median of
    per-image CER (one bad image moves the pooled number, the median barely)."""
    total = sum((r[1] for r in rows), collections.Counter())
    post = sum((r[3] for r in rows), collections.Counter())
    pooled_cer, wer, recall, precision, f1, critical = rates(total)
    per_image = [cer(r[1]) for r in rows]
    return (pooled_cer, statistics.mean(per_image), statistics.median(per_image), wer,
            recall, precision, f1, critical, share(total, "critical2"),
            share(total, "critical_bag"), rates(post)[5], cer(post),
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


def tsv_text(tsv, min_conf=0, tiny_block=0):
    """Plain text from a Tesseract TSV: words joined per line. Optionally
    drops words with confidence below min_conf, and blocks with at most
    tiny_block characters in all (specks and stamp edges read as text)."""
    words = [c for c in (row.split("\t") for row in tsv.splitlines())
             if len(c) == 12 and c[0] == "5" and c[11].strip()]
    block_chars = collections.Counter()
    for c in words:
        block_chars[c[2]] += len(c[11].strip())
    lines = {}
    for c in words:
        if float(c[10]) >= min_conf and block_chars[c[2]] > tiny_block:
            lines.setdefault(tuple(c[2:5]), []).append(c[11])
    return "\n".join(" ".join(ws) for ws in lines.values())


def noise_sweep(samples, variant, jobs, confs=(0, 10, 20, 30, 40, 50, 60), tiny=(0, 2, 4)):
    """Experiment: drop noise words before output, by confidence and by
    tiny isolated blocks. One TSV read per page; every filter is simulated."""
    psm, dpi, thresholding, model = variant
    with ThreadPoolExecutor(jobs) as pool:
        prepared = list(pool.map(lambda smp: prepare(smp[1]), samples))
        outs = list(pool.map(lambda p: tesseract(p[0], psm, dpi, thresholding, model, tsv=True), prepared))
    rows = {}
    for n, k in itertools.product(confs, tiny):
        name = (f"drop conf < {n}" if n else "keep all") + (f", blocks <= {k} chars" if k else "")
        rows[name] = []
        for (sample, _, truth), (png, prep_s), (tsv, ocr_s) in zip(samples, prepared, outs):
            text = tsv_text(tsv, n, k)
            rows[name].append((sample, score(truth, text), prep_s + ocr_s,
                               score(truth, app.postprocess_text(text))))
    table(rows)


def adaptive_sweep(samples, jobs, thresholds=(0, 50, 60, 65, 70, 75, 80, 85, 90, 101)):
    """Experiment: read with the fast models; when their mean word confidence
    is below a threshold, read again with the best models and keep the more
    confident result. Both reads run once per page; every threshold is then
    simulated from them. 0 = never rerun, 101 = always."""
    with ThreadPoolExecutor(jobs) as pool:
        prepared = list(pool.map(lambda smp: prepare(smp[1]), samples))
        tasks = [(i, model) for i in range(len(samples)) for model in ("fast", "best")]
        outs = dict(zip(tasks, pool.map(
            lambda t: tesseract(prepared[t[0]][0], 3, 0, 0, t[1], tsv=True), tasks)))

    rows, reruns = {}, {}
    for t in thresholds:
        name = "fast only" if t == 0 else "always both" if t > 100 else f"rerun if conf < {t}"
        rows[name], reruns[name] = [], 0
        for i, (sample, _, truth) in enumerate(samples):
            (fast, fast_s), (best, best_s) = outs[i, "fast"], outs[i, "best"]
            conf_fast, conf_best = app.mean_word_confidence(fast), app.mean_word_confidence(best)
            seconds = prepared[i][1] + fast_s
            tsv = fast
            if conf_fast < t:
                reruns[name] += 1
                seconds += best_s
                tsv = best if conf_best > conf_fast else fast
            text = tsv_text(tsv)
            rows[name].append((sample, score(truth, text), seconds,
                               score(truth, app.postprocess_text(text))))
    rows["best only"] = [
        (sample, score(truth, tsv_text(outs[i, "best"][0])), prepared[i][1] + outs[i, "best"][1],
         score(truth, app.postprocess_text(tsv_text(outs[i, "best"][0]))))
        for i, (sample, _, truth) in enumerate(samples)
    ]
    table({f"{n} (reran {reruns[n]}/{len(samples)})" if n in reruns else n: r for n, r in rows.items()})
    print("\n| Image | fast conf | best conf |\n| --- | --- | --- |")
    for i, (sample, _, _) in enumerate(samples):
        print(f"| {sample} | {app.mean_word_confidence(outs[i, 'fast'][0]):.1f} "
              f"| {app.mean_word_confidence(outs[i, 'best'][0]):.1f} |")


def machine():
    """Timings only compare on the same machine; the Pi is the one that counts."""
    try:
        with open("/proc/device-tree/model") as f:  # Raspberry Pi
            return f.read().strip("\0\n")
    except OSError:
        pass
    try:  # Raspberry Pi inside Docker, where /proc/device-tree is hidden
        with open("/proc/cpuinfo") as f:
            model = [l.split(":", 1)[1].strip() for l in f if l.startswith("Model")]
        if model:
            return model[0]
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
    p.add_argument("--psm", default="3,4,6")
    p.add_argument("--dpi", default="0,300", help="0 = don't pass --dpi")
    p.add_argument("--thresh", default="0,2", help="thresholding_method: 0 Otsu, 2 Sauvola")
    p.add_argument("--model", default="fast,best")
    p.add_argument("--adaptive", action="store_true",
                   help="instead of the variant grid: sweep the fast-then-best rerun threshold "
                        "(psm 3)")
    p.add_argument("--noise", action="store_true",
                   help="instead of the variant grid: sweep dropping low-confidence words and "
                        "tiny blocks (first value of each variant option)")
    p.add_argument("--jobs", type=int, default=os.cpu_count(),
                   help="parallel tesseract runs; 1 gives the cleanest timings")
    a = p.parse_args()

    split = lambda s, f=str: [f(x) for x in s.split(",")]
    variants = list(itertools.product(split(a.psm, int), split(a.dpi, int),
                                      split(a.thresh, int), split(a.model)))
    # RapidOCR ignores psm/dpi/thresh: one run is enough.
    variants = sorted({(0, 0, 0) + v[3:] if v[3].startswith("rapidocr") else v for v in variants})
    global JOBS
    JOBS = a.jobs
    if ("best" in split(a.model) or a.adaptive) and not os.path.isdir(app.TESSDATA_BEST_DIR):
        sys.exit(f"model best needs {app.TESSDATA_BEST_DIR} (set TESSDATA_BEST_DIR)")
    samples = load_samples(a.dirs)
    if a.adaptive:
        print(f"{len(samples)} images, adaptive sweep, psm 3; "
              f"timings on {machine()}, {a.jobs} parallel jobs\n")
        return adaptive_sweep(samples, a.jobs)
    if a.noise:
        print(f"{len(samples)} images, noise sweep, {label(variants[0])}; "
              f"timings on {machine()}, {a.jobs} parallel jobs\n")
        return noise_sweep(samples, variants[0], a.jobs)
    print(f"{len(samples)} images, {len(variants)} variants; "
          f"timings on {machine()}, {a.jobs} parallel jobs\n")
    report(run(samples, variants, a.jobs), default=(3, 0, 0, "fast"))
    if [os.path.normpath(d) for d in a.dirs] == ["Examples"]:
        print("\n" + BASELINE)
    print("\nRAM peak per job: " + ", ".join(
        f"{m} {rss / 2**20:.0f} MB" for m, rss in sorted(PEAK_RSS.items())))


if __name__ == "__main__":
    main()
