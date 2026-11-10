# Benchmark results

## 2026-11-10 (3) — noise filter, holdout, running on the Pi

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

| Variant | s/image, Pi 5, 4 jobs |
| --- | --- |
| v2, psm 3, fast | not run yet |
| v2, psm 4, best | not run yet |

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
