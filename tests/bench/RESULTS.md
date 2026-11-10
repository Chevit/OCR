# Benchmark results

RapidOCR/PP-OCR code removed, see tag bench-paddleocr-experiment.

## 2026-11-10 (14) — baseline preparation removed, last baseline numbers

The service now has one preparation (v2: lighting evened out, text scaled
to ~30 px, levelled); `PREPROCESS` and the old baseline path (sized by
megapixels only) are gone, and the bench lost `--preprocess`. Variant
labels drop the "v2, " prefix. Last baseline run before removal, pages
1–10 (Latin ICD-10 ground truth), offline bench image, Docker on an Apple
M4 Pro, 4 jobs:

| Variant | CER pooled | Word recall | Word F1 | Critical (positional) | Critical, 2+ chars | Critical, POSTPROCESS=1 |
| --- | --- | --- | --- | --- | --- | --- |
| v2, psm 3, fast (service default) | 21.6% | 84.3% | 78.7% | 72.0% | 76.3% | 72.2% |
| baseline, psm 3, fast (removed) | 34.0% | 70.2% | 71.4% | 61.8% | 67.4% | 62.3% |

`python -m tests.bench.bench Examples` prints the baseline row's numbers
under its report for comparison (`BASELINE` in `bench.py`). Earlier
baseline numbers for the other sets are in sections (1)–(11).

## 2026-11-10 (13) — crops-2: crops of pages 11–19 (seen)

`Examples/crops-2/`: 9 crops, one per holdout page 11–19, ICD-10 letters
Latin. The pages were seen (image-12 was studied), so this is a sanity
check for Фрагмент, not a holdout. 136 critical tokens (one ≈ 0.7
points). **Raspberry Pi 5 Model B Rev 1.1, bench image (offline), 4
jobs**; a Mac run gives identical scores (same files on both):

| Variant | CER pooled | Word recall | Word F1 | Critical (positional) | Critical, POSTPROCESS=1 | Critical, 2+ chars | s/image | RAM peak per job |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v2, psm 6, best | **9.8%** | **85.8%** | **84.7%** | 77.2% | 77.2% | 79.3% | 9.3 | 92 MB |
| **v2, psm 6, fast (Фрагмент)** | 10.3% | 83.2% | 82.0% | 75.7% | 76.5% | 76.9% | 4.1 | 68 MB |
| v2, psm 3, best | 13.1% | 84.5% | 84.5% | 76.5% | 76.5% | 79.3% | 9.3 | 92 MB |
| v2, psm 3, fast (default) | 13.8% | 82.5% | 82.4% | 77.2% | 77.9% | 79.3% | 4.1 | 68 MB |

Per image, fast, psm 3 vs psm 6 (CER / recall / critical):

| Image | psm 3 | psm 6 |
| --- | --- | --- |
| image-11 | 2.5% / 86% / 40% | 2.5% / 86% / 40% |
| image-12 | 25.5% / 91% / 71% | 25.7% / 86% / 61% |
| image-13 | 6.9% / 88% / 88% | 4.5% / 88% / 100% |
| image-14 | 3.8% / 85% / 62% | 3.8% / 85% / 62% |
| image-15 | 12.7% / 79% / 75% | 10.7% / 78% / 75% |
| image-16 | 1.5% / 92% / 90% | 1.5% / 92% / 90% |
| image-17 | 53.8% / 35% / 33% | 25.8% / 52% / 33% |
| image-18 | 0.8% / 98% / 100% | 0.8% / 98% / 100% |
| image-19 | 2.7% / 88% / 88% | 2.7% / 87% / 88% |

- psm 6 confirms on CER: 13.8% → 10.3% (fast), mostly image-17 (53.8% →
  25.8%, recall 35% → 52%) and image-13, 15. Five crops are unchanged.
- Critical tokens are a wash: psm 6 fast −1.5 points (2 tokens), all on
  image-12 (71% → 61%), offset by image-13 (88% → 100%). image-12 is the
  crop whose page had the line-pitch scaling bug ((4)).
- best with psm 6 is the most accurate (CER 9.8%, recall 85.8%, critical
  +1.5 over fast) at 2.3x the time (9.3 vs 4.1 s per crop), under 15 s.
  fast vs best for Фрагмент stays open for holdout-2.
- POSTPROCESS=1: +0.8 points for psm 6 fast, none for best.

Command:

```bash
sudo docker compose run --build --rm bench python -m tests.bench.bench Examples/crops-2 \
  --preprocess v2 --psm 3,6 --dpi 0 --thresh 0 --model fast,best --jobs 4
```

## 2026-11-10 (12) — ICD-10 ground truth in Latin, POSTPROCESS for codes

**Ground truth**: ICD-10 codes always get a Latin letter now. 14 codes
with a Cyrillic look-alike letter were changed in every `.gt.txt`:
`Н66.1` (image-2 page and crop), `К60.5`, `К61.3`, `К64.1` (holdout and
crops-2 image-16), and image-14 in crops-2. Military unit numbers
(`в/ч А3215`) stay Cyrillic. Rule and a grep check are in the bench README.

**POSTPROCESS** (`fix_icd10`, runs after the per-word fixes): a token that
is a whole ICD-10 code gets a Latin letter for А/В/Е/К/М/Н/О/Р/С/Т/Х/І,
also when glued to other text (`0м(Н90.3)`), and "X00. 1" becomes "X00.1".
Before, a code inside a mostly Cyrillic word (`Н66.1)Хронічна`) was
switched back to Cyrillic by the per-word fix; that is fixed. Unit tests
cover the changes and words that must stay (`в/ч А3215`, `Б12.1`,
`Н66.1мг`, `12.03. 2024`, `С5-С6`, ...).

Re-scored, v2 fast, offline bench image, **Docker on an Apple M4 Pro, 4
jobs** (scores are deterministic, Pi gives the same):

| Set | Variant | CER pooled | Word recall | Critical (positional) | Critical, POSTPROCESS=1 | Critical, 2+ chars |
| --- | --- | --- | --- | --- | --- | --- |
| Pages 1–10 | **psm 3 (default)** | 21.6% | 84.3% | 72.0% | 72.2% | 76.3% |
| Pages 1–10 | psm 6 | 26.7% | 83.7% | 73.4% | 73.7% | 76.6% |
| Crops (10) | psm 3 | 11.9% | 80.9% | 60.2% | 63.4% | 58.0% |
| Crops (10) | **psm 6 (Фрагмент)** | 9.8% | 84.0% | 65.9% | 69.1% | 65.0% |
| Holdout 11–19 (seen) | psm 3 (default) | 30.2% | 77.7% | 63.0% | 63.3% | 64.6% |
| Holdout 11–19 (seen) | psm 6 | 31.5% | 81.9% | 67.5% | 67.8% | 68.4% |

- The corrected ground truth moves the default on pages 72.2% → 72.0%
  (fast reads image-2's `( Н66.1` with a Cyrillic letter, which now
  counts as wrong) and leaves crops unchanged.
- POSTPROCESS for codes: +3.2 points on crops (4 of 123 tokens: the
  image-2 codes), +0.2–0.3 on pages and holdout. CER is unchanged
  (±0.1).
- psm 6 on whole pages: more critical tokens (+1.4 / +4.5 points) but
  much worse CER (+5.1 / +1.3) and WER (reading order); the default for
  pages stays psm 3, psm 6 only for Фрагмент.
- crops-2 (crops of pages 11–19) was being filled while this ran; see
  (13) for its numbers.

Command (per set):

```bash
docker compose run --build --rm bench python -m tests.bench.bench Examples/crops \
  --preprocess v2 --psm 3,6 --dpi 0 --thresh 0 --model fast --jobs 4
```

## 2026-11-10 (11) — crops re-run with 10 crops

`Examples/crops/` now has 10 crops (image-6 to image-10 added; image-1 to
image-5 unchanged, image-2's mixed Latin/Cyrillic H still in its
`.gt.txt`). 123 critical tokens (one token ≈ 0.8 points). Offline bench
image, **Docker on an Apple M4 Pro, 4 jobs** (not a Pi timing), 14
variants; selected rows:

| Variant | CER pooled | Word recall | Word F1 | Critical (positional) | Critical, 2+ chars | s/image | RAM peak per job |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2, rapidocr (v6 small det + eslav rec) | 9.6% | 66.7% | 65.8% | **82.1%** | **83.0%** | 1.8 | 341 MB |
| **v2, psm 6, fast** | **9.8%** | **84.1%** | **82.0%** | 65.9% | 65.0% | 1.2 | 97 MB |
| v2, psm 4, fast | 10.2% | 83.5% | 81.1% | 69.1% | 67.0% | 1.2 | 97 MB |
| v2, psm 6, best | 10.5% | 83.2% | 81.4% | 71.5% | 69.0% | 1.9 | 97 MB |
| v2, psm 4, best | 11.1% | 83.7% | 81.5% | 72.4% | 69.0% | 1.8 | 97 MB |
| v2, psm 3, fast (service default) | 11.9% | 81.0% | 79.8% | 60.2% | 58.0% | 1.2 | 97 MB |
| v2, psm 3, best | 12.5% | 82.3% | 80.9% | 69.1% | 66.0% | 1.8 | 97 MB |
| baseline, psm 3, fast | 18.0% | 75.5% | 76.3% | 45.5% | 45.0% | 0.9 | 97 MB |

Per image, v2 fast psm 3 vs psm 6 (CER / recall / critical):

| Image | psm 3 | psm 6 |
| --- | --- | --- |
| image-1 | 1.2% / 94% / 80% | 1.2% / 94% / 80% |
| image-2 | 3.7% / 89% / 17% | 3.7% / 89% / 17% |
| image-3 | 15.8% / 57% / 50% | 15.5% / 57% / 50% |
| image-4 | 19.5% / 50% / 25% | 16.9% / 60% / 75% |
| image-5 | 0.9% / 95% / 100% | 0.9% / 95% / 100% |
| image-6 | 10.1% / 91% / 100% | 6.6% / 91% / 100% |
| image-7 | 2.5% / 93% / 64% | 2.4% / 94% / 64% |
| image-8 | 12.2% / 92% / 78% | 17.5% / 90% / 75% |
| image-9 | 16.4% / 87% / 47% | 14.9% / 88% / 47% |
| image-10 | 35.7% / 54% / 32% | 18.5% / 72% / 56% |

- **On crops, psm 6 fast is the best Tesseract choice on CER, recall and
  F1** (9.8% / 84.1% / 82.0% vs the default's 11.9% / 81.0% / 79.8%),
  +5.7 points of critical tokens at the same speed. It is better or equal
  on 9 of 10 crops; the big gains are image-10 (CER 35.7% → 18.5%) and
  image-4. image-8 is the exception (CER 12.2% → 17.5%).
- psm 4 is close to psm 6 (more critical tokens: 69.1%, slightly higher
  CER). best adds 5–9 points of critical tokens at ~1.5x the time, with
  higher CER.
- v2 beats baseline on crops too (psm 3 fast: CER 18.0% → 11.9%).
- RapidOCR still leads on critical tokens (+16 over psm 6 fast) and loses
  17 points of recall; closed on Pi time in (9).
- psm 6 was clearly worse on full pages ((1)), so this argues for a
  separate crop / text-block mode (psm 6), not a new default.

Command (Mac):

```bash
docker compose run --build --rm bench python -m tests.bench.bench Examples/crops \
  --preprocess baseline,v2 --psm 3,4,6 --dpi 0 --thresh 0 --model fast,best,rapidocr-v6-small --jobs 4
```

**Raspberry Pi 5 Model B Rev 1.1, bench image (offline), 4 jobs**
(v2, psm 3 and 6):

| Variant | CER pooled | Word recall | Word F1 | Critical (positional) | Critical, 2+ chars | s/image | RAM peak per job |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **v2, psm 6, fast** | **9.8%** | **84.1%** | **82.0%** | 65.9% | 65.0% | 4.5 | 89 MB |
| v2, psm 6, best | 10.5% | 83.2% | 81.4% | 71.5% | 69.0% | 9.9 | 95 MB |
| v2, psm 3, fast (service default) | 11.9% | 81.0% | 79.8% | 60.2% | 58.0% | 4.6 | 89 MB |
| v2, psm 3, best | 12.5% | 82.3% | 80.9% | 69.1% | 66.0% | 9.5 | 95 MB |

Scores and per-image numbers are identical to the Mac.

- psm 6 costs nothing on the Pi (4.5 vs 4.6 s per crop); best takes
  ~2.2x fast (9.5–9.9 s), under the 15 s limit on crops.
- Confirms: for crops, psm 6 fast beats the default on every quality
  measure at the same speed. A crop mode with psm 6 is the candidate;
  the full-page default stays psm 3.

Pi command (after copying `Examples/crops/` over; `Examples/` is git-ignored):

```bash
sudo docker compose run --build --rm bench python -m tests.bench.bench Examples/crops \
  --preprocess v2 --psm 3,6 --dpi 0 --thresh 0 --model fast,best --jobs 4
```

## 2026-11-10 (10) — cropped text regions (`Examples/crops/`)

Five crops of text regions (240–426 px tall strips, 980–2114 px wide) cut
from pages of the selection set, each with its own `.gt.txt`. 22 critical
tokens in all: one token is 4.5 points, so critical-token differences
here are mostly noise. Offline bench image, **Docker on an Apple M4 Pro,
4 jobs** (not a Pi timing). Selected rows (all 14 variants run):

| Variant | CER pooled | Word recall | Word F1 | Critical (positional) | Critical, 2+ chars | s/image | RAM peak per job |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2, rapidocr (v6 small det + eslav rec) | 7.2% | 63.5% | 62.8% | 81.8% | 89.5% | 1.6 | 279 MB |
| v2, psm 6, best | 10.4% | 75.7% | 75.1% | 77.3% | 78.9% | 1.9 | 89 MB |
| v2, psm 3, best | 12.0% | 75.7% | 74.7% | 72.7% | 73.7% | 1.8 | 89 MB |
| v2, psm 6, fast | 8.1% | 78.6% | 77.3% | 59.1% | 68.4% | 1.2 | 80 MB |
| **v2, psm 3, fast (service default)** | 8.9% | 75.7% | 74.7% | 50.0% | 57.9% | 1.2 | 80 MB |
| v2, psm 4, fast | 8.9% | 75.7% | 74.7% | 50.0% | 57.9% | 1.2 | 80 MB |
| baseline, psm 3, fast | 10.3% | 72.1% | 71.9% | 54.5% | 57.9% | 0.9 | 80 MB |

Per image, default vs rapidocr (CER / recall / critical): image-1 1.2/94/80
vs 6.1/64/100; image-2 3.7/89/17 vs 7.0/62/67; image-3 15.8/57/50 vs
11.7/57/75; image-4 19.5/50/25 vs 7.8/58/75; image-5 0.9/95/100 vs
4.9/79/100.

- **psm 6 helps on crops** (one block of text): fast CER 8.9% → 8.1%,
  recall +2.9, critical +9 points (2 tokens). On image-4, psm 3 splits
  the strip into fragments ("20,10, 2026", "09.11.26"); psm 6 reads the
  lines in order. On full pages psm 6 was clearly worse ((1)), so it
  would only fit a "crop / text block" mode.
- **best** reads more numbers (+22.7 points with psm 3) but its CER is
  higher on crops (12.0% vs 8.9%).
- **Default critical 50% is partly a ground-truth artefact.** image-2's
  `.gt.txt` (and the main set's `image-2.gt.txt`) types the ICD codes with
  mixed letters: `H66.1` and `H90.3` with Latin H, `( Н66.1` with
  Cyrillic Н; the print looks the same. fast reads `(Н90.3)` with
  Cyrillic Н, so a correct reading scores as wrong. fast's real misses
  there are spaces inside codes: `H66. 1`, `Н66. 1`, `2, 0м`.
- RapidOCR again leads on critical tokens and loses on word recall; the
  Pi time gate closed it ((9)).

**Raspberry Pi 5 Model B Rev 1.1, bench image (offline), 4 jobs**
(v2 only):

| Variant | CER pooled | Word recall | Word F1 | Critical (positional) | Critical, 2+ chars | s/image |
| --- | --- | --- | --- | --- | --- | --- |
| v2, psm 6, fast | 8.1% | 78.6% | 77.3% | 59.1% | 68.4% | 4.7 |
| **v2, psm 3, fast (service default)** | 8.9% | 75.7% | 74.7% | 50.0% | 57.9% | 4.8 |
| v2, psm 6, best | 10.4% | 75.7% | 75.1% | 77.3% | 78.9% | 8.3 |
| v2, psm 3, best | 12.0% | 75.7% | 74.7% | 72.7% | 73.7% | 9.0 |

Scores are identical to the Mac. Per image, psm 3 vs psm 6 (fast)
differ only on image-4 (19.5/50/25 → 16.9/60/75) and image-3 (CER
15.8% → 15.5%); the psm 6 gain on crops is one strip.

- Every variant is well under the 15 s limit on a crop (fast 4.7–4.8 s,
  best 8.3–9.0 s; s/image includes preparation and the orientation check).
- best costs ~1.8x fast for +18 to +23 points of critical tokens (4–5
  tokens) and higher CER. With 5 crops this isn't enough to pick a
  crop-mode default; more crops would be needed.

Command (Mac; on the Pi with `sudo` and `--preprocess v2 --psm 3,6
--model fast,best`):

```bash
docker compose run --build --rm bench python -m tests.bench.bench Examples/crops \
  --preprocess baseline,v2 --psm 3,4,6 --dpi 0 --thresh 0 --model fast,best,rapidocr-v6-small --jobs 4
```

## 2026-11-10 (9) — detector comparison: PP-OCRv5 mobile, PP-OCRv6 tiny, small

Recognizer unchanged (eslav PP-OCRv5 mobile; PP-OCRv6 rec has no
Cyrillic). Detectors are the official PaddlePaddle ONNX files on Hugging
Face (`PaddlePaddle/PP-OCRv5_mobile_det_onnx`, `PP-OCRv6_tiny_det_onnx`,
`PP-OCRv6_small_det_onnx`, `inference.onnx` at pinned commits, SHA-256 in
the Dockerfile and `rapid.py`), baked into the offline bench image. No
arena, one thread, one process per job, as before.

Detector settings come from each repo's `inference.yml`; what it leaves
out comes from PaddleX 3.7.2's text-detection predictor, not RapidOCR's
defaults:

| | v5 mobile | v6 tiny | v6 small | RapidOCR default (used in (4), (8)) |
| --- | --- | --- | --- | --- |
| Resize | longest side 960 (`resize_long`) | longest side ≤ 960 (predictor default) | same | shortest side ≥ 736, page ≤ 2000 |
| Normalize | ImageNet mean/std | ImageNet | ImageNet | 0.5 / 0.5 |
| DB thresh / box_thresh / unclip | 0.3 / 0.6 / 1.5 | 0.2 / 0.4 / 1.4 | 0.2 / 0.45 / 1.4 | 0.3 / 0.5 / 1.6 |
| max_candidates, dilation | 1000, off | 3000, off | 3000, off | 1000, on |

PaddleOCR's general OCR *pipeline* overrides these (shortest side ≥ 64,
i.e. near full resolution, 0.3 / 0.6 / 1.5); not tested. RapidOCR's page
limit (≤ 2000 px before detection) is kept for every variant, so the
recognizer crops lines from the same image.

Selection set, offline bench image, **Docker on an Apple M4 Pro, 4 jobs
(not a Pi timing)**:

| Variant | CER pooled | Word recall | Word F1 | Critical (positional) | Critical, 2+ chars | s/image | RAM peak per job |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v6 small det + eslav rec | 19.2% | 70.8% | 67.6% | **84.4%** | **85.9%** | 4.5 | 356 MB |
| v6 tiny det + eslav rec | 19.2% | 71.0% | 67.5% | 83.4% | 84.5% | 4.5 | 353 MB |
| v5 mobile det (official settings) + eslav rec | 23.8% | 66.7% | 66.2% | 73.4% | 74.6% | 4.2 | 348 MB |
| v5 mobile det (RapidOCR settings, (8)) | 19.4% | 73.4% | 70.1% | 82.6% | 85.6% | 4.7 | 760 MB |
| v2, psm 3, fast (service default) | 21.6% | 84.3% | 78.8% | 72.2% | 76.6% | 2.9 | 141 MB |

- v6 small reads the most critical tokens (+12.2 points over fast), v6
  tiny is close; word recall stays 13 points below Tesseract (и/й for і/ї).
- v5 mobile loses 9 points with its official settings: a whole page at
  960 px is too small for it. v6 reads well at the same size.
- **RAM halves** (~350 MB vs 760 MB): detection now runs on a ≤ 960 px
  image. Under the 500 MB gate on the Mac.
- **Time is the recognizer's.** Split for the 9 pages, one job (Mac):
  detection 1.2 s (v5 mobile), 0.9 s (v6 tiny), 2.0 s (v6 small);
  recognition 24–27 s, ~95% of RapidOCR's time, for 430–455 lines. On
  the Pi the v5 mobile run took +27.9 s/image over fast ((8)); a faster
  detector can't take that under +5 s. Confirmed on the Pi below.

**Raspberry Pi 5 Model B Rev 1.1, bench image (offline), 4 jobs**:

| Variant | CER pooled | Word recall | Word F1 | Critical (positional) | Critical, 2+ chars | s/image | Over fast | RAM peak per job |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v6 small det + eslav rec | 19.2% | 70.8% | 67.6% | **84.4%** | **85.9%** | 36.3 | **+25.6** | 360 MB |
| v6 tiny det + eslav rec | 19.2% | 71.0% | 67.5% | 83.4% | 84.5% | 38.0 | **+27.3** | 356 MB |
| v5 mobile det (official settings) + eslav rec | 23.8% | 66.7% | 66.2% | 73.4% | 74.6% | 34.1 | **+23.4** | 349 MB |
| v2, psm 3, fast (service default) | 21.6% | 84.3% | 78.8% | 72.2% | 76.6% | 10.7 | — | 143 MB |

Scores are identical to the Mac run; only time and RAM differ.

- **RAM gate passes** (349–360 MB ≤ 500 MB). **Time gate fails** for
  every detector: +23.4 to +27.3 s/image over fast (limit 5 s), 3.2–3.6x
  fast. Detector size barely matters (v5 mobile with official settings
  is the fastest and reads worst); the eslav recognizer is the cost, as
  the Mac split showed.
- **Decision: second engine stays closed.** No Tesseract + PP-OCR merge.
  Reopening would need a recognizer several times faster on the Pi (e.g.
  re-reading only the number/date lines Tesseract is unsure of), not a
  different detector.

Command used (in the `OCR` folder, after `git pull`):

```bash
sudo docker compose run --build --rm bench python -m tests.bench.bench Examples \
  --preprocess v2 --psm 3 --dpi 0 --thresh 0 \
  --model fast,rapidocr-v5-mobile,rapidocr-v6-tiny,rapidocr-v6-small --jobs 4
```

## 2026-11-10 (8) — RapidOCR with the PP-OCRv5 mobile detector

Last engine experiment, timing first. `rapidocr-mobile` = RapidOCR's own
PP-OCRv5 mobile detector (`ch_PP-OCRv5_det_mobile.onnx`, 4.6 MB, URL and
SHA-256 from rapidocr 3.10.0's `default_models.yaml`, baked into the bench
image) + the same eslav recognizer; otherwise the `rapidocr` settings (no
memory arena, one onnxruntime thread per job, own process per job).

**Gate** for the next step (line-level merge: Tesseract text, PP-OCR
numbers): on the Pi, ≤ 5 s/image over fast and ≤ 500 MB per job.
Otherwise the second engine is closed.

Selection set, offline bench image, **Docker on an Apple M4 Pro, 4 jobs
(not a Pi timing)**:

| Variant | CER pooled | Word recall | Word F1 | Critical (positional) | Critical, 2+ chars | s/image | RAM peak per job |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2, rapidocr-mobile | 19.4% | 73.4% | 70.1% | **82.6%** | **85.6%** | 4.7 | 760 MB |
| v2, rapidocr (server det, from (7)) | 20.6% | 73.0% | 69.4% | 81.4% | 82.1% | 20.4 | 2.2 GB |
| v2, psm 3, fast (service default) | 21.6% | 84.3% | 78.8% | 72.2% | 76.6% | 2.9 | 140 MB |

Per image (CER / recall / critical), fast vs rapidocr-mobile: image-1
1.4/94/95 vs 5.2/74/95; image-10 5.1/93/77 vs 8.2/72/100; image-2
6.1/88/91 vs 13.2/80/86; image-3 54.3/62/25 vs 48.5/52/100; image-4
43.3/81/84 vs 39.6/69/59; image-5 18.8/84/50 vs 10.4/75/70; image-6
44.1/89/92 vs 49.7/75/92; image-8 8.6/89/76 vs 9.8/77/92; image-9
52.8/59/29 vs 33.7/67/51.

- The mobile detector reads at least as well as the server one (+1.2
  points positional, +3.5 on 2+ chars) at 4x less time on the Mac.
- RAM: 760 MB per job on the Mac, over the 500 MB gate. The Pi measured
  the server detector lower than the Mac (1.9 vs 2.2 GB), so the Pi run
  decides.
- Time: +1.8 s/image over fast on the Mac. The server detector was 7x
  fast on the Mac and 11x on the Pi; at that ratio the mobile detector
  lands near +6–7 s on the Pi, around the 5 s gate.

**Raspberry Pi 5 Model B Rev 1.1, bench image (offline), 4 jobs**:

| Variant | CER pooled | Word recall | Word F1 | Critical (positional) | Critical, 2+ chars | s/image | RAM peak per job |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2, rapidocr-mobile | 19.4% | 73.4% | 70.1% | **82.6%** | **85.6%** | **38.3** | **760 MB** |
| v2, psm 3, fast (service default) | 21.6% | 84.3% | 78.8% | 72.2% | 76.6% | 10.4 | 135 MB |

Scores and per-image numbers are identical to the Mac run; only time and
RAM differ.

- **Gate failed on both counts**: +27.9 s/image over fast (limit 5 s;
  3.7x fast, far worse than the Mac's 1.6x) and 760 MB per job (limit
  500 MB). The +6–7 s estimate above was wrong: on the Pi the mobile
  detector is still 3x slower than the Mac ratio predicted.
- **Decision: second engine closed.** No line-level merge (Tesseract
  text, PP-OCR numbers). RapidOCR stays in the bench only; Tesseract fast
  psm 3 stays the default, `model=best` the choice for number-heavy pages.

Command used (in the `OCR` folder, after `git pull`):

```bash
sudo docker compose run --build --rm bench python -m tests.bench.bench Examples \
  --preprocess v2 --psm 3 --dpi 0 --thresh 0 --model fast,rapidocr-mobile --jobs 4
```

## 2026-11-10 (7) — positional critical tokens, all variants re-scored

The critical-token count was order-free: a page counted a date as read if
it appeared anywhere, so a right number in the wrong place, or table
borders read as "1", scored (found with the hybrid experiment, section (6)
on branch `experiment/hybrid-reread`). Now output words are aligned to
ground-truth words (rapidfuzz Levenshtein opcodes on word sequences) and a
token counts only if the words aligned to it contain exactly that token.
"2+ chars" is the same positional count for tokens of two or more
characters. The old column is kept once as "order-free, deprecated".

Images 1–10 (9 with ground truth), offline bench image (Docker on an
Apple M4 Pro, 4 jobs; s/image is not a Pi timing), ranked by pooled CER:

| Variant | CER pooled | Word recall | Word F1 | Critical (positional) | Critical, 2+ chars | Critical (order-free, deprecated) | s/image |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2, rapidocr (PP-OCRv5 det + eslav rec) | 20.6% | 73.0% | 69.4% | **81.4%** | **82.1%** | 90.6% | 20.4 |
| v2, psm 3, best | 21.4% | 84.9% | 79.2% | 73.4% | 75.3% | 81.4% | 5.5 |
| v2, psm 3, fast + hybrid rule C | 21.5% | 84.6% | 79.0% | 72.5% | 77.3% | 78.9% | 3.6 |
| v2, psm 3, fast (service default) | 21.6% | 84.3% | 78.8% | 72.2% | 76.6% | 78.4% | 2.8 |
| v2, psm 4, best | 21.6% | 84.9% | 79.6% | 76.7% | 77.0% | 83.4% | 5.3 |
| v2, psm 4, fast | 22.2% | 83.9% | 78.9% | 73.4% | 76.3% | 77.2% | 2.7 |
| baseline, psm 3, fast | 34.0% | 70.2% | 71.4% | 62.0% | 67.7% | 70.2% | 2.6 |

Hybrid rule C reads Tesseract's TSV; plain fast text from the TSV scores
the same as the default row, so its +0.3 (+0.7 on 2+ chars) is the re-read.

- Every variant loses 4–9 points; the ranking of the main choices holds,
  except psm 4 now beats psm 3 on critical tokens (fast 73.4% vs 72.2%,
  best 76.7% vs 73.4%), where the order-free count had psm 3 ahead.
- RapidOCR's lead over the default shrinks from 12.2 to 9.2 points
  (5.5 on 2+ chars); still not adoptable on the Pi (116.5 s/image, 1.9 GB).
- Hybrid rule C: +0.3 points, confirming "not adopted".

## 2026-11-10 (5) — straightening fills corners with paper gray (image-17 fixed)

`straighten()` (used by both paths and by `turn_upright`) now fills the
uncovered corners with the page's 90th-percentile gray instead of 255; see
"image-17: why baseline reads nothing" below. image-17 baseline: 0 → 1435
characters read. Tests: a tilted gray page gets gray corners; real
Tesseract on image-17 (local only, `Examples/` is git-ignored). Synthetic
gray pages didn't reproduce the blackout, so that test uses the real page.

Local Mac, psm 3, dpi -, thresh 0, fast, 4 jobs; old → new:

| Set / path | CER pooled | Critical tokens |
| --- | --- | --- |
| Selection 1–10, v2 (default) | 22.0% → 21.6% | 78.4% → 78.4% |
| Selection 1–10, baseline | 34.8% → 33.7% | 68.7% → 67.0% |
| Old holdout 11–19, v2 | 30.3% → 30.3% | 71.4% → 71.4% |
| Old holdout 11–19, baseline | 38.4% → 34.9% | 66.4% → 67.2% |

v2 pages that changed (flattened paper is ~243–255, not exactly 255, so the
fill moves a little). Critical tokens are unchanged on every page:

| Image | Char errors | Words found |
| --- | --- | --- |
| image-5 | 388 → 325 | 176 → 185 |
| image-9 | 1118 → 1118 | 173 → 174 |
| image-10 | 104 → 108 (+4) | 248 → 248 |
| image-17 | 888 → 889 (+1) | 122 → 122 |

image-1, 2, 3, 4, 6, 8: identical.

Known and accepted: baseline on the selection set loses 1.7 points of
critical tokens, almost all from image-9 (30 → 23 of 51, while its CER
improves 55.9% → 49.3%); image-3 and image-6 lose one each, image-8 gains
two. Not investigated: the baseline path is due for removal after holdout-2.

## 2026-11-10 (4) — scaling fix, image-17, RapidOCR experiment

### Scaling fix (image-12)

Text-height scaling may now shrink a page only when it is over
`TESSERACT_MAX_MEGAPIXELS`; otherwise the scale is never below the
megapixel (baseline) scale. A pitch misread as a multiple of the line
spacing can no longer shrink the page. Unit test: a synthetic page whose
row profile peaks at 4x the real pitch.

Pages whose scale changed: image-12 (622×816 → 1792×2355) and image-3
(1312×984 → 2309×1732, also shrunk before). Every other page is prepared
exactly as before.

Selection set (images 1–6, 8–10), Apple M4 Pro, 12 jobs:

| Variant | CER pooled | CER median | Word recall | Word F1 | Critical tokens | s/image |
| --- | --- | --- | --- | --- | --- | --- |
| v2, psm 3, best | 21.7% | 21.3% | 84.4% | 78.8% | 81.1% | 6.3 |
| **v2, psm 3, fast (service default)** | 22.0% | 22.9% | 83.8% | 78.4% | 78.4% | 3.6 |
| v2, psm 4, best | 22.0% | 25.2% | 84.7% | 79.4% | 83.4% | 5.7 |
| v2, psm 4, fast | 22.1% | 25.0% | 83.7% | 78.6% | 78.2% | 3.7 |
| baseline, psm 3, fast | 34.8% | 39.5% | 69.7% | 71.2% | 68.7% | 3.6 |

- v2 fast: CER 22.2% → 22.0%, recall 83.7% → 83.8%, critical tokens
  78.9% → 78.4%. The critical drop is image-3 alone: 3 of its 4 tokens → 1
  of 4 with fast (best reads all 4), while its CER improves 63.3% → 53.3%
  and recall 58% → 62%. Baseline rows are unchanged (the fix is v2 only).

Old holdout (images 11–19), **seen — sanity check only**: image-12 was
studied to find this failure, so these numbers can't confirm the fix.
Confirmation waits for holdout-2.

| Variant | CER pooled | CER median | Word recall | Word F1 | Critical tokens |
| --- | --- | --- | --- | --- | --- |
| v2, psm 3, best | 30.1% | 25.6% | 78.9% | 76.2% | 71.1% |
| **v2, psm 3, fast** | 30.3% | 25.9% | 77.6% | 75.0% | 71.4% |
| v2, psm 4, fast | 31.1% | 26.5% | 78.8% | 74.7% | 74.8% |
| baseline, psm 3, fast | 38.4% | 33.5% | 67.4% | 70.4% | 66.4% |

- image-12 (v2 fast): 74.6% / 15% / 10% → 42.6% / 73% / 71% (CER /
  recall / critical); baseline had 42.7% / 71% / 71%.
- image-19 reads 25.9% / 76% / 66% now vs 24.3% / 80% / 68% in (3), with
  an identical prepared page (same size, run twice, same result). Its
  `.gt.txt` was saved at 14:10, close to the 14:15 holdout commit, so the
  earlier run likely used an older text. Not caused by the fix.

### image-17: why baseline reads nothing (fixed in (5) above)

Not rotation (OSD: 0°, confidence 2.7), not inversion (mean gray 176, under
the 128 threshold only when dark). It is **the white fill from
straightening**:

- The photo is dim: after autocontrast the paper is gray (~177), text ~85–130.
- Baseline levels a 1.5° tilt and fills the uncovered corners with pure
  white (`fillcolor=255`): 5.3% of the page becomes 255.
- Tesseract's Otsu then splits "gray paper vs white wedges" (threshold
  212), not ink vs paper: the whole sheet turns black, layout analysis
  calls it one picture, and no text lines are found.
- Same page and tilt, only the fill changed: white 0 words, paper-gray
  (177) 202 words, not straightened 165 words.
- v2 escapes it because shadow evening makes the paper white (mean 243),
  so the white fill blends in. `turn_upright` uses the same white fill,
  harmless after v2 for the same reason. Matters only while the baseline
  path exists; a fill of the page's median gray would fix it there.

### RapidOCR + PP-OCRv5 (experiment, bench only)

`tests/bench/rapid.py`: RapidOCR 3.10.0, onnxruntime 1.31.1, models from
monkt/paddleocr-onnx at commit 7b02d0a (pinned by SHA-256): PP-OCRv5 det
(the repo has only the **server** detector, 88 MB) + eslav PP-OCRv5 mobile
rec. Same v2 preparation and orientation check; RapidOCR's own defaults
after that (it resizes to ≤ 2000 px), no angle classifier, one onnxruntime
thread per job, each job its own process.

Selection set, **Apple M4 Pro, 4 jobs (no Pi run yet)**:

| Variant | CER pooled | CER median | Word recall | Word precision | Word F1 | Critical tokens | s/image | RAM peak per job |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v2, rapidocr | 20.7% | 16.4% | 72.8% | 66.1% | 69.3% | **90.3%** | 11.6 | 2.3–3.6 GB |
| v2, psm 3, best | 21.7% | 21.3% | 84.4% | 73.8% | 78.8% | 81.1% | 4.8 | 0.2 GB |
| v2, psm 3, fast | 22.0% | 22.9% | 83.8% | 73.7% | 78.4% | 78.4% | 2.7 | 0.1 GB |

Per image (CER / recall / critical), fast vs rapidocr:

| Image | fast | rapidocr |
| --- | --- | --- |
| image-1 | 1.7% / 94% / 95% | 5.2% / 74% / 95% |
| image-10 | 5.3% / 93% / 73% | 8.4% / 70% / 96% |
| image-2 | 6.2% / 88% / 91% | 15.6% / 77% / 91% |
| image-3 | 53.3% / 62% / 25% | 55.0% / 54% / 75% |
| image-4 | 42.7% / 81% / 90% | 40.1% / 70% / 80% |
| image-5 | 22.9% / 80% / 60% | 16.4% / 76% / 80% |
| image-6 | 44.3% / 88% / 100% | 48.4% / 81% / 100% |
| image-8 | 8.5% / 89% / 78% | 8.7% / 77% / 97% |
| image-9 | 53.6% / 59% / 63% | 39.2% / 62% / 69% |

- **Critical tokens +12 points** over fast (+9 over best): numbers, dates
  and codes read much better (image-8, 208 tokens: 78% → 97%).
- **Word recall −11 points**: the eslav recognizer writes Russian и/й/э
  where Ukrainian has і/ї/є ("ликарську", "Украйни", "Довидка"), so many
  words miss by one letter. CER barely notices; word search would.
- **Cost**: 4.3x fast's time on the Mac; peak RAM 2.3–3.6 GB per job
  (varies between runs), 20–30x Tesseract's. Four jobs would need ~10–14
  GB, more than a Pi 5 has, so it couldn't run at `OCR_CONCURRENCY=4` as is.
- **Offline**: the `bench` compose service has the models and bench
  packages baked into its image (Dockerfile stage `bench`, models pinned by
  SHA-256) and runs with `network_mode: none`, so nothing can be uploaded
  and nothing is fetched at run time. RapidOCR gets explicit paths for every
  file; its downloader (the only network code in rapidocr) is blocked, so a
  missing file fails loudly. Checked in Docker on the Mac (aarch64, service
  image's Tesseract 5.5.0, 4 jobs): name lookup fails, only loopback is up,
  and the bench passes with RapidOCR numbers identical to the native run
  (20.7% / 72.8% / 90.3%, 21.0 s/image, 2.2 GB per job; fast 22.0% /
  83.8% / 78.4%, 2.9 s).
- **Raspberry Pi 5, bench image (offline), 4 jobs**, selection set
  (commit 78c350c, before the pool-lock fix; scores and per-job RAM are
  measured per process, so they are unaffected):

| Variant | CER pooled | Word recall | Word F1 | Critical tokens | s/image | RAM peak per job |
| --- | --- | --- | --- | --- | --- | --- |
| v2, rapidocr | 20.7% | 72.8% | 69.3% | **90.3%** | **116.5** | 1.9 GB |
| v2, psm 3, best | 21.7% | 84.6% | 78.8% | 81.4% | 27.3 | 144 MB |
| v2, psm 3, fast (service default) | 22.0% | 83.8% | 78.1% | 78.4% | 10.3 | 144 MB |

  Scores are identical to the Mac and Docker runs (the engines are
  deterministic); only time and RAM differ.

- **Decision: RapidOCR is not adopted as an engine.** On the Pi it takes
  116.5 s/image, 11x fast and ~8x the 15 s limit, and four jobs need ~7.8
  GB of RAM. Its gain is critical tokens (+12 points), its loss word recall
  (−11 points, и/й for і/ї). Revisit only with a mobile-size PP-OCRv5
  detector and a recognizer that keeps Ukrainian letters, e.g. reading
  only number/date regions.

Rerun on the Pi (in the `OCR` folder, after `git pull`):

```bash
sudo docker compose run --build --rm bench python -m tests.bench.bench Examples \
  --preprocess v2 --psm 3 --dpi 0 --thresh 0 --model fast,best,rapidocr --jobs 4
```

## 2026-11-10 (3) — noise filter, holdout, Pi timings

### Running the bench on the Pi

The service image has no `tests/` and no rapidfuzz, and production
`requirements.txt` stays without bench dependencies. Run the bench in a
throwaway container of the service image: `--build` rebuilds it from the
checkout (the app is baked in at build time), `tests/` and `Examples/` are
mounted, and rapidfuzz is installed into that container only (`--rm` deletes
it afterwards). The tessdata_best models are already in the image.

```bash
# Chosen variant and the candidates for the default model
sudo docker compose run --build --rm -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -v ./tests:/app/tests -v ./Examples:/app/Examples ocr \
  sh -c "pip install -q --root-user-action=ignore -r tests/bench/requirements.txt && \
    python -m tests.bench.bench Examples --preprocess v2 --psm 3,4 --dpi 0 --thresh 0 --model fast,best --jobs 4"

# Adaptive model (fast, rerun with best below a confidence threshold)
sudo docker compose run --rm -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -v ./tests:/app/tests -v ./Examples:/app/Examples ocr \
  sh -c "pip install -q --root-user-action=ignore -r tests/bench/requirements.txt && \
    python -m tests.bench.bench Examples --adaptive --preprocess v2 --jobs 4"
```

Checked with Docker on the Mac: the image's Tesseract 5.5.0 gives v2 psm 3
fast 22.2% pooled CER, as the native 5.5.4 does. The first line of the output
names the machine; on the Pi it reads `Raspberry Pi 5 ...`.

**Default model decision**: if psm 4 + best takes ≤ 15 s/image there at
`--jobs 4`, it becomes the default (`model=best`, psm 4 for text mode).
Otherwise fast psm 3 stays.

Raspberry Pi 5 Model B Rev 1.1, 4 parallel jobs, service image (Tesseract
5.5.0), selection set:

| Variant | CER pooled | CER median | Word recall | Word F1 | Critical tokens | s/image |
| --- | --- | --- | --- | --- | --- | --- |
| v2, psm 3, best | 21.8% | 21.3% | 84.6% | 78.8% | 81.4% | 24.6 |
| **v2, psm 3, fast (service default)** | 22.2% | 22.6% | 83.8% | 78.0% | 78.9% | 9.1 |
| v2, psm 4, best | 22.2% | 24.4% | 84.5% | 79.1% | 83.1% | 24.6 |
| v2, psm 4, fast | 22.8% | 24.6% | 83.5% | 78.5% | 77.9% | 9.4 |

Adaptive sweep on the Pi (psm 3, same set):

| Variant | CER pooled | Critical tokens | Pages rerun | s/image |
| --- | --- | --- | --- | --- |
| fast only | 22.2% | 78.9% | 0/9 | 10.0 |
| rerun if conf < 65 | 22.0% | 79.2% | 1/9 | 10.6 |
| rerun if conf < 70 / 75 | 22.0% | 79.4% | 2/9 | 12.4 |
| rerun if conf < 80 | 22.0% | 79.4% | 4/9 | 18.0 |
| rerun if conf < 90 | 22.0% | 80.1% | 7/9 | 23.3 |
| always both | 21.9% | 80.4% | 9/9 | 25.6 |
| best only | 21.8% | 81.4% | — | 19.7 |

(best only: 19.7 s here vs 24.6 s in the grid run; each run has a different
mix of jobs sharing the CPU at once, so compare timings within one run.)

- **Decision: fast psm 3 stays the default.** psm 4 + best takes 24.6
  s/image, over the 15 s limit, for +4.2 points of critical tokens; best is
  2.7x slower than fast on the Pi (1.7x on the M4 Pro).
- Adaptive: no threshold pays off on the Pi either; at most +0.5 points of
  critical tokens for 1.2x the time (conf < 70).
- `model=best` stays a choice in the UI for pages where numbers matter more
  than waiting.

### Dropping noise words (not adopted)

v2, psm 3, fast; selection set (9 pages). Words with confidence below N are
dropped before output; "blocks ≤ k chars" also drops Tesseract blocks with at
most k characters in all (specks, stamp edges). `--noise` simulates every
filter from one TSV read per page. Adoption rule: F1 rises with no more than
1 point of recall lost.

| Filter | CER pooled | Word recall | Word precision | Word F1 | Critical tokens |
| --- | --- | --- | --- | --- | --- |
| keep all | 22.2% | 83.7% | 73.5% | 78.2% | 78.9% |
| keep all, blocks ≤ 2 chars | 22.3% | 83.6% | 73.5% | 78.2% | 78.9% |
| keep all, blocks ≤ 4 chars | 22.3% | 83.6% | 73.5% | 78.2% | 78.9% |
| drop conf < 10 | 21.8% | 83.2% | 75.0% | 78.9% | 78.7% |
| drop conf < 20 | 21.6% | 82.9% | 76.3% | 79.4% | 78.7% |
| drop conf < 30 | 21.4% | 82.7% | 77.8% | 80.2% | 78.2% |
| drop conf < 40 | 21.1% | 82.3% | 79.2% | 80.8% | 77.9% |
| drop conf < 50 | 21.2% | 81.4% | 80.7% | 81.1% | 76.9% |
| drop conf < 60 | 21.4% | 80.8% | 82.1% | 81.5% | 76.4% |

- Tiny blocks: no effect at all on these pages.
- Confidence: N = 10, 20, 30 pass the rule (F1 +0.7 / +1.2 / +2.0, recall
  −0.5 / −0.8 / −1.0). Every N also loses critical tokens (−0.2 / −0.2 /
  −0.7), and a dropped word is gone without a trace, while word check
  already marks the same words red for the reader to fix. **Not adopted**;
  if wanted, N = 20 is the safe choice, for text output only.

### Holdout (images 11–19), reported once for the final choice

Ground truth for images 11–19 moved to `Examples/holdout/` (files 11–17 were
named `image-N..gt.txt` and were not picked up). Apple M4 Pro, 12 jobs.

| Variant | CER pooled | CER median | Word recall | Word F1 | Critical tokens | s/image |
| --- | --- | --- | --- | --- | --- | --- |
| v2, psm 4, best | 34.9% | 26.6% | 71.8% | 71.4% | 65.5% | 5.5 |
| v2, psm 4, fast | 35.1% | 26.5% | 70.8% | 70.6% | 64.7% | 3.3 |
| v2, psm 3, best | 35.1% | 24.4% | 70.7% | 71.9% | 63.6% | 5.8 |
| **v2, psm 3, fast (service default)** | 35.3% | 25.0% | 69.6% | 70.8% | 62.2% | 3.2 |
| baseline, psm 3, best | 38.3% | 34.2% | 68.4% | 71.4% | 66.7% | 5.6 |
| baseline, psm 3, fast | 38.4% | 33.5% | 67.4% | 70.4% | 66.4% | 3.3 |
| baseline, psm 4, best | 39.1% | 34.1% | 67.5% | 70.5% | 65.5% | 5.5 |
| baseline, psm 4, fast | 39.1% | 33.5% | 66.8% | 69.9% | 65.0% | 3.0 |

Per image, psm 3 fast (CER / recall / critical tokens):

| Image | Critical tokens in truth | baseline | v2 |
| --- | --- | --- | --- |
| image-11 | 32 | 52.5% / 51% / 47% | 25.0% / 80% / 72% |
| image-12 | 58 | 42.7% / 71% / 71% | **74.6% / 15% / 10%** |
| image-13 | 27 | 32.7% / 80% / 52% | 42.6% / 73% / 56% |
| image-14 | 22 | 37.7% / 61% / 68% | 9.7% / 87% / 86% |
| image-15 | 64 | 26.6% / 82% / 88% | 27.6% / 83% / 83% |
| image-16 | 20 | 21.0% / 79% / 55% | 8.4% / 92% / 65% |
| image-17 | 17 | 100.0% / 0% / 0% | 55.9% / 54% / 41% |
| image-18 | 27 | 33.5% / 63% / 74% | 14.6% / 87% / 93% |
| image-19 | 90 | 20.4% / 83% / 72% | 24.3% / 80% / 68% |

- **v2 holds on CER, recall and F1** (pooled CER 38.4% → 35.3%, median
  33.5% → 25.0%, better on 6 of 9 pages), **but not on critical tokens**
  (66.4% → 62.2%). The whole gap is image-12.
- **image-12**: after shadow evening, `line_pitch` reads 114 px instead of
  the real 25.6 px (a multiple of the line spacing), so the page is shrunk by
  the 0.5x floor (1200×1600 → 622×816) instead of enlarged. Same failure
  class as the image-2 pitch fix. Not tuned here, to keep the holdout honest.
- **Baseline path kept** until the image-12 failure is fixed and verified on
  new pages.

## 2026-11-10 (2) — v2 default, new metrics, adaptive model, image-6/10

Same selection set (9 pages), Apple M4 Pro, 12 parallel jobs. **No Pi
timings yet** (pending, see below).

- **v2 is now the service default** (psm 3, fast); the baseline path stays
  until the holdout confirms.
- **New metrics**: word precision and F1 (beside recall = "words found"), and
  **critical tokens**: dates, ICD-10 codes, dosages (мг/мл/г/од) and other
  numbers from the ground truth, share read exactly.

### Main variants with the new metrics

| Variant | CER pooled | CER mean | CER median | WER | Word recall | Word precision | Word F1 | Critical tokens | Critical, POSTPROCESS=1 | CER, POSTPROCESS=1 | s/image |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v2, psm 3, dpi -, thresh 0, best | 21.8% | 26.4% | 21.3% | 42.9% | 84.4% | 73.7% | 78.7% | 81.1% | 81.4% | 21.8% | 6.0 |
| v2, psm 4, dpi -, thresh 0, best | 22.1% | 27.4% | 25.2% | 41.7% | 84.8% | 74.8% | 79.4% | 83.4% | 83.6% | 22.1% | 5.9 |
| v2, psm 3, dpi -, thresh 0, fast (service default) | 22.2% | 27.6% | 22.9% | 45.1% | 83.7% | 73.5% | 78.2% | 78.9% | 79.2% | 22.2% | 3.5 |
| v2, psm 4, dpi -, thresh 0, fast | 22.3% | 28.3% | 25.0% | 42.9% | 83.7% | 74.1% | 78.6% | 78.9% | 79.2% | 22.3% | 3.3 |
| baseline, psm 4, dpi -, thresh 0, best | 33.1% | 38.9% | 38.5% | 49.1% | 72.3% | 74.1% | 73.2% | 79.2% | 79.4% | 33.1% | 4.8 |
| baseline, psm 4, dpi -, thresh 0, fast | 33.1% | 38.7% | 38.1% | 50.5% | 71.8% | 73.6% | 72.7% | 73.9% | 74.2% | 33.1% | 3.2 |
| baseline, psm 3, dpi -, thresh 0, best | 34.7% | 39.6% | 39.5% | 49.3% | 70.9% | 74.0% | 72.4% | 75.7% | 75.9% | 34.7% | 5.0 |
| baseline, psm 3, dpi -, thresh 0, fast | 34.8% | 39.3% | 39.5% | 51.0% | 69.7% | 72.7% | 71.2% | 68.7% | 69.0% | 34.8% | 3.2 |

| Image | v2, psm 3, dpi -, thresh 0, fast: CER / recall / critical | v2, psm 3, dpi -, thresh 0, best: CER / recall / critical |
| --- | --- | --- |
| image-1 | 1.7% / 94% / 95% | 1.4% / 94% / 95% |
| image-10 | 5.3% / 93% / 73% | 5.9% / 93% / 85% |
| image-2 | 6.3% / 87% / 91% | 7.1% / 88% / 95% |
| image-3 | 63.3% / 58% / 75% | 53.1% / 75% / 100% |
| image-4 | 42.7% / 81% / 90% | 42.5% / 81% / 90% |
| image-5 | 22.9% / 80% / 60% | 21.3% / 81% / 70% |
| image-6 | 44.3% / 88% / 100% | 44.4% / 91% / 100% |
| image-8 | 8.5% / 89% / 78% | 8.3% / 89% / 80% |
| image-9 | 53.6% / 59% / 63% | 53.2% / 60% / 59% |

- **Critical tokens: v2 fast 78.9% vs baseline 68.7%.** `best` models help
  here more than CER shows: psm 4 + best 83.4%, psm 3 + best 81.1%, at ~1.7x
  the time. **POSTPROCESS=1 adds only ~0.3 points**: OCR mistakes in these
  tokens are mostly digits misread as other digits, not look-alike letters.
- **Word precision ~74% everywhere**: outputs carry ~35% extra words
  (stamps, signatures, noise). Recall is what v2 improves.

### Adaptive model (fast, rerun with best when mean word confidence < T)

`python -m tests.bench.bench --adaptive --preprocess v2` (psm 3):

| Variant | CER pooled | CER mean | CER median | WER | Word recall | Word precision | Word F1 | Critical tokens | Critical, POSTPROCESS=1 | CER, POSTPROCESS=1 | s/image |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best only | 21.8% | 26.4% | 21.3% | 42.9% | 84.4% | 73.7% | 78.7% | 81.1% | 81.4% | 21.8% | 5.7 |
| always both (reran 9/9) | 21.8% | 26.4% | 21.3% | 43.1% | 84.3% | 73.8% | 78.7% | 80.9% | 81.1% | 21.8% | 7.6 |
| rerun if conf < 90 (reran 7/9) | 21.8% | 26.4% | 21.3% | 43.3% | 84.2% | 73.7% | 78.6% | 80.9% | 81.1% | 21.8% | 6.9 |
| rerun if conf < 80 (reran 4/9) | 21.8% | 26.3% | 21.3% | 44.5% | 84.1% | 73.9% | 78.6% | 79.4% | 79.7% | 21.8% | 5.6 |
| rerun if conf < 85 (reran 5/9) | 21.8% | 26.3% | 21.3% | 44.5% | 84.2% | 73.9% | 78.7% | 79.4% | 79.7% | 21.8% | 5.8 |
| rerun if conf < 65 (reran 1/9) | 22.0% | 26.5% | 22.9% | 44.7% | 84.0% | 73.8% | 78.6% | 79.2% | 79.4% | 22.0% | 3.8 |
| rerun if conf < 70 (reran 2/9) | 22.0% | 26.5% | 22.9% | 44.7% | 84.0% | 73.8% | 78.6% | 79.2% | 79.4% | 22.0% | 4.3 |
| rerun if conf < 75 (reran 2/9) | 22.0% | 26.5% | 22.9% | 44.7% | 84.0% | 73.8% | 78.6% | 79.2% | 79.4% | 22.0% | 4.3 |
| fast only (reran 0/9) | 22.2% | 27.6% | 22.9% | 45.1% | 83.7% | 73.5% | 78.2% | 78.9% | 79.2% | 22.2% | 3.6 |
| rerun if conf < 50 (reran 0/9) | 22.2% | 27.6% | 22.9% | 45.1% | 83.7% | 73.5% | 78.2% | 78.9% | 79.2% | 22.2% | 3.6 |
| rerun if conf < 60 (reran 0/9) | 22.2% | 27.6% | 22.9% | 45.1% | 83.7% | 73.5% | 78.2% | 78.9% | 79.2% | 22.2% | 3.6 |

| Image | fast conf | best conf |
| --- | --- | --- |
| image-1 | 93.5 | 94.2 |
| image-10 | 92.3 | 91.2 |
| image-2 | 88.9 | 90.4 |
| image-3 | 61.1 | 64.3 |
| image-4 | 78.0 | 77.2 |
| image-5 | 79.2 | 80.1 |
| image-6 | 80.4 | 84.1 |
| image-8 | 89.4 | 89.5 |
| image-9 | 69.9 | 69.3 |

- No threshold pays off: rerunning 4–5 of 9 pages (T = 80–85) gains 0.4
  points of CER and 0.5 points of critical tokens for ~1.6x the time; always
  taking the better of both gains 2 points of critical tokens for ~2.1x.
  Confidence separates pages poorly (image-4/5/6 sit at 78–80 with very
  different error rates). **Not adopted**; if critical tokens matter more
  than speed, `best` alone (psm 4) is the simpler lever, decided on the Pi.

### Why v2 is worse on image-6 (+4.8) and image-10 (+2.0)

v2 = background flattening + scaling by text height. Split on these pages
(psm 3, fast; CER / word recall / critical):

| | baseline | v2 | v2 without flattening |
| --- | --- | --- | --- |
| image-6 | 39.5% / 90% / 100% | 44.3% / 88% / 100% | 40.3% / 86% / 100% |
| image-10 | 3.3% / 93% / 77% | 5.3% / 93% / 73% | 4.8% / 93% / 77% |

- image-6: mostly **reading order** (recall and critical tokens barely move).
- image-10: ~0.5 points from flattening, ~1.5 from scaling (1.66x vs
  baseline's 1.49x). Single-page, 1–2 point effects: within noise for 9 pages.
- **Skipping flattening when the lighting map is flat was tried and
  rejected.** Lighting spread (p95−p5)/p95 of the page centre: 0.14–0.18 on
  images 4, 6, 8, 9, 10; 0.29–0.48 on 1, 3, 5. Skipping below 0.2 helps 6, 9,
  10 slightly but loses image-4 (42.7% → 60.7%) and image-8 (8.5% → 11.0%):
  pooled CER 22.2% → 24.8%, recall 83.7% → 78.5%, critical 78.9% → 73.7%.

### Pi timings

See section (3): run inside the service image.

## 2026-11-10 (1) — selection set, white redaction (baseline + all variants)

- **Data**: Examples/ images 1–6, 8–10 (9 pages; image-7 has no text yet).
  Holdout (images 11–19) not typed yet, so not run. Files as of 11:09.
  Earlier real-set numbers are discarded (black redaction bars; image-1
  and image-3 re-redacted since).
- **Code**: commit "Measure tilt on the central 70% of the page". Includes
  the 180° both-ways check and the line-pitch fix; both apply to every
  variant, so baseline numbers already contain them.
- **Timings**: Apple M4 Pro, 12 parallel jobs. Not the Pi: speed decisions
  wait for a Pi run (`--jobs 4`).
- **Words found** = share of ground-truth words present in the output in
  any order. CER also punishes reading order (a stamp block read before
  the header), so pages like image-6 score ~40% CER with ~90% words found.

### Summary

| | CER pooled | CER mean | CER median | Words found | s/image (M4 Pro) |
| --- | --- | --- | --- | --- | --- |
| Current service (baseline, psm 3, fast) | 34.8% | 39.3% | 39.5% | 69.7% | 3.5 |
| v2, psm 3, fast | 22.2% | 27.6% | 22.9% | 83.7% | 3.6 |
| v2, psm 4, fast | 22.3% | 28.3% | 25.0% | 83.7% | 3.6 |
| v2, psm 3, best | 21.8% | 26.4% | 21.3% | 84.4% | 6.6 |

- **v2 wins clearly** at the same speed: −12.6 points pooled CER, +14 points
  words found. Biggest gains: image-5 (97% → 23%: baseline inverts it as a
  "dark theme" page), image-1 (14% → 2%), image-4 (61% → 43%).
- **psm 3 ≈ psm 4** with v2 (psm 6 worse); **`--dpi 300`** no gain.
- **`best` models**: ~0.4 points for ~1.8x the time. Not worth it as default.
- **Sauvola (`thresholding_method=2`)** hurts with v2 (+4–6 points on matched variants); without
  v2 it helps some pages and hurts others. Unlike the synthetic set, not a
  win on real pages.
- **POSTPROCESS=1** moves CER by ≤0.1 point: few look-alike errors on these
  pages. Its value is search and copy of codes, not CER.
- **Still weak**: image-3 (~60% words found, blurry photo with stamps),
  image-9 (~57%), image-6 (reading order, words ~88% fine).
- **Redaction affects scores**: white boxes on grayish paper are sharp
  rectangles too (image-1: 27.7% → 15.0% when filled with the paper colour
  instead). Prefer paper-coloured fill.

### Auto-crop to the page (tried, not adopted yet)

`PREPROCESS=v3` = v2 that first crops to the page (lighting map ≥ half the
paper brightness; longest light run of rows, then columns). It crops only
image-2 (phone UI) and image-4 (desk) here: pooled CER 21.7% vs 22.3% for
v2 (psm 4, fast), words found equal. The rotation failures it targeted are
fixed by the 180° both-ways check (image-2 is still reported as 180° after
cropping) and by measuring tilt on the page centre (image-4, image-5).
Revisit when the holdout or new failures show pages it would help.

### Per image (CER, words found in brackets)

| Image | baseline, psm 3, dpi -, thresh 0, fast | baseline, psm 4, dpi -, thresh 0, fast | v2, psm 3, dpi -, thresh 0, fast | v2, psm 4, dpi -, thresh 0, fast | v2, psm 4, dpi -, thresh 0, best |
| --- | --- | --- | --- | --- | --- |
| image-1 | 14.4% (81%) | 14.4% (81%) | 1.7% (94%) | 1.7% (94%) | 1.4% (94%) |
| image-10 | 3.3% (93%) | 3.8% (94%) | 5.3% (93%) | 5.3% (93%) | 5.8% (93%) |
| image-2 | 6.3% (87%) | 6.4% (88%) | 6.3% (87%) | 6.4% (88%) | 6.8% (89%) |
| image-3 | 62.8% (38%) | 75.8% (37%) | 63.3% (58%) | 66.5% (62%) | 58.0% (79%) |
| image-4 | 60.7% (48%) | 49.4% (63%) | 42.7% (81%) | 46.2% (82%) | 45.3% (82%) |
| image-5 | 97.3% (0%) | 97.0% (0%) | 22.9% (80%) | 25.0% (76%) | 25.2% (77%) |
| image-6 | 39.5% (90%) | 38.1% (91%) | 44.3% (88%) | 45.2% (88%) | 45.2% (89%) |
| image-8 | 13.6% (84%) | 16.2% (84%) | 8.5% (89%) | 6.6% (90%) | 6.7% (90%) |
| image-9 | 55.9% (62%) | 47.4% (63%) | 53.6% (59%) | 51.9% (56%) | 52.5% (59%) |

### All variants

| Variant | CER pooled | CER mean | CER median | WER pooled | Words found | CER pooled, POSTPROCESS=1 | s/image |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2, psm 3, dpi -, thresh 0, best | 21.8% | 26.4% | 21.3% | 42.9% | 84.4% | 21.8% | 6.6 |
| v2, psm 4, dpi -, thresh 0, best | 22.1% | 27.4% | 25.2% | 41.7% | 84.8% | 22.1% | 6.7 |
| v2, psm 3, dpi -, thresh 0, fast | 22.2% | 27.6% | 22.9% | 45.1% | 83.7% | 22.2% | 3.6 |
| v2, psm 4, dpi -, thresh 0, fast | 22.3% | 28.3% | 25.0% | 42.9% | 83.7% | 22.3% | 3.6 |
| v2, psm 3, dpi 300, thresh 0, best | 22.6% | 27.9% | 22.8% | 42.3% | 84.1% | 22.6% | 6.6 |
| v2, psm 4, dpi 300, thresh 0, best | 22.7% | 27.1% | 23.8% | 43.0% | 84.9% | 22.7% | 6.7 |
| v2, psm 3, dpi 300, thresh 0, fast | 22.9% | 29.2% | 22.3% | 43.7% | 83.7% | 22.9% | 3.6 |
| v2, psm 4, dpi 300, thresh 0, fast | 23.3% | 29.1% | 25.1% | 45.3% | 83.7% | 23.3% | 3.6 |
| v2, psm 4, dpi -, thresh 2, fast | 25.8% | 33.4% | 43.6% | 49.7% | 80.8% | 25.8% | 3.8 |
| v2, psm 6, dpi -, thresh 0, best | 26.1% | 34.6% | 26.9% | 55.5% | 84.6% | 26.1% | 7.3 |
| v2, psm 6, dpi 300, thresh 0, best | 26.1% | 34.6% | 26.9% | 55.5% | 84.6% | 26.1% | 6.9 |
| v2, psm 4, dpi -, thresh 2, best | 26.2% | 33.5% | 44.6% | 49.1% | 82.3% | 26.2% | 6.9 |
| v2, psm 3, dpi -, thresh 2, best | 26.2% | 35.7% | 41.8% | 46.5% | 82.1% | 26.2% | 6.4 |
| v2, psm 3, dpi -, thresh 2, fast | 26.4% | 36.3% | 40.3% | 48.6% | 80.7% | 26.4% | 3.5 |
| v2, psm 6, dpi -, thresh 0, fast | 26.6% | 35.0% | 26.5% | 57.4% | 84.4% | 26.6% | 3.9 |
| v2, psm 6, dpi 300, thresh 0, fast | 26.6% | 35.0% | 26.5% | 57.4% | 84.4% | 26.6% | 3.8 |
| v2, psm 6, dpi -, thresh 2, best | 29.3% | 36.8% | 48.4% | 62.4% | 82.7% | 29.3% | 7.4 |
| v2, psm 6, dpi -, thresh 2, fast | 29.5% | 37.0% | 48.9% | 62.8% | 81.9% | 29.5% | 3.9 |
| baseline, psm 4, dpi -, thresh 2, best | 30.2% | 38.0% | 44.0% | 48.1% | 76.5% | 30.2% | 6.0 |
| v2, psm 3, dpi 300, thresh 2, best | 30.2% | 35.7% | 47.4% | 46.5% | 76.0% | 30.2% | 5.9 |
| baseline, psm 4, dpi -, thresh 2, fast | 30.3% | 37.9% | 44.8% | 48.5% | 76.1% | 30.3% | 3.6 |
| v2, psm 3, dpi 300, thresh 2, fast | 30.4% | 36.3% | 47.2% | 47.9% | 75.5% | 30.4% | 3.4 |
| v2, psm 4, dpi 300, thresh 2, fast | 30.6% | 38.1% | 44.8% | 49.4% | 75.7% | 30.6% | 3.5 |
| v2, psm 4, dpi 300, thresh 2, best | 30.6% | 38.0% | 44.5% | 47.5% | 76.6% | 30.6% | 6.2 |
| baseline, psm 6, dpi -, thresh 0, best | 30.9% | 37.8% | 47.2% | 58.2% | 76.0% | 30.9% | 6.7 |
| baseline, psm 6, dpi 300, thresh 0, best | 30.9% | 37.8% | 47.2% | 58.2% | 76.0% | 30.9% | 6.9 |
| baseline, psm 3, dpi 300, thresh 2, fast | 31.0% | 38.2% | 46.0% | 48.9% | 75.2% | 31.1% | 3.5 |
| baseline, psm 3, dpi 300, thresh 2, best | 31.1% | 38.2% | 42.7% | 47.9% | 75.7% | 31.1% | 5.8 |
| baseline, psm 6, dpi -, thresh 0, fast | 31.2% | 38.2% | 53.5% | 60.2% | 74.5% | 31.2% | 3.8 |
| baseline, psm 6, dpi 300, thresh 0, fast | 31.2% | 38.2% | 53.5% | 60.2% | 74.5% | 31.2% | 3.8 |
| baseline, psm 6, dpi 300, thresh 2, fast | 31.2% | 40.0% | 45.1% | 58.2% | 76.6% | 31.2% | 3.9 |
| baseline, psm 6, dpi 300, thresh 2, best | 31.2% | 40.1% | 44.5% | 57.0% | 77.3% | 31.2% | 6.8 |
| v2, psm 6, dpi 300, thresh 2, best | 31.8% | 40.0% | 48.7% | 59.0% | 78.5% | 31.8% | 5.6 |
| baseline, psm 6, dpi -, thresh 2, fast | 31.9% | 41.0% | 48.8% | 64.9% | 77.7% | 31.9% | 4.0 |
| v2, psm 6, dpi 300, thresh 2, fast | 32.0% | 40.3% | 49.9% | 60.6% | 77.6% | 32.0% | 3.5 |
| baseline, psm 3, dpi -, thresh 2, fast | 32.2% | 38.8% | 46.3% | 49.0% | 75.9% | 32.2% | 3.5 |
| baseline, psm 6, dpi -, thresh 2, best | 32.4% | 41.7% | 48.8% | 64.2% | 78.2% | 32.4% | 7.5 |
| baseline, psm 3, dpi -, thresh 2, best | 32.6% | 39.6% | 47.6% | 48.4% | 76.1% | 32.7% | 5.8 |
| baseline, psm 4, dpi 300, thresh 2, fast | 32.7% | 39.5% | 46.7% | 50.9% | 75.8% | 32.8% | 3.6 |
| baseline, psm 4, dpi 300, thresh 2, best | 32.9% | 39.9% | 42.7% | 50.1% | 75.7% | 32.9% | 6.0 |
| baseline, psm 4, dpi -, thresh 0, best | 33.1% | 38.9% | 38.5% | 49.1% | 72.3% | 33.1% | 5.7 |
| baseline, psm 4, dpi -, thresh 0, fast | 33.1% | 38.7% | 38.1% | 50.5% | 71.8% | 33.1% | 3.4 |
| baseline, psm 4, dpi 300, thresh 0, fast | 33.4% | 38.6% | 40.8% | 51.4% | 70.9% | 33.4% | 3.5 |
| baseline, psm 4, dpi 300, thresh 0, best | 33.5% | 38.5% | 41.9% | 50.1% | 71.0% | 33.5% | 5.7 |
| baseline, psm 3, dpi 300, thresh 0, fast | 34.0% | 39.6% | 40.3% | 49.5% | 68.9% | 34.1% | 3.4 |
| baseline, psm 3, dpi 300, thresh 0, best | 34.2% | 39.3% | 39.8% | 48.5% | 69.4% | 34.2% | 5.3 |
| baseline, psm 3, dpi -, thresh 0, best | 34.7% | 39.6% | 39.5% | 49.3% | 70.9% | 34.7% | 5.5 |
| baseline, psm 3, dpi -, thresh 0, fast (baseline) | 34.8% | 39.3% | 39.5% | 51.0% | 69.7% | 34.8% | 3.5 |
