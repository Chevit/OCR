# Benchmark results

## 2026-11-10 — selection set, white redaction (baseline + all variants)

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
