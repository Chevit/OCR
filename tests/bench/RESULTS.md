# Benchmark results

## 2026-11-10 — selection set, white redaction (baseline + all variants)

- **Data**: Examples/ images 1–6, 8–10 (9 pages; image-7 has no text yet).
  Holdout (images 11–19) not typed yet, so not run. Files as of 11:09;
  image-1 and image-3 were re-redacted during the session, and earlier
  numbers are discarded.
- **Code**: commit after "Make line pitch ignore weak and negative peaks"
  (v2 fix found on this run: image-2's black phone UI gave a false pitch and
  halved the page).
- **Timings**: Apple M4 Pro, 12 parallel jobs. Not the Pi; speed decisions
  wait for a Pi run (`--jobs 4`).

### Summary

| | CER pooled | CER mean | CER median | WER pooled | s/image (M4 Pro) |
| --- | --- | --- | --- | --- | --- |
| Current service (baseline, psm 3, fast) | 36.7% | 42.0% | 39.5% | 54.2% | 3.6 |
| v2, psm 4, dpi 300, fast | 27.6% | 34.4% | 22.0% | 45.8% | 3.6 |
| v2, psm 4, dpi 300, best | 27.5% | 34.2% | 20.3% | 44.5% | 6.2 |

- **v2 wins** on pooled, mean and median CER at the same speed; mostly from
  image-5 (97% → 20%, a page beside a dark strip) and image-1. The `best`
  models add almost nothing for ~1.7x the time.
- **psm 4 ≥ psm 3 > psm 6** with v2; `--dpi 300` is a small plus.
- **Sauvola (`thresholding_method=2`) hurts with v2** (v2 already evens the
  light); without v2 it helps some pages and hurts others. Unlike the
  synthetic set, it is not a win on real pages.
- **POSTPROCESS=1** changes CER by ≤0.1%: these pages have few look-alike
  errors. Its value is in search and copy of codes, not CER.
- **Still failing**: image-3 (~67%), image-4 (~80% with v2), image-9 (~53%),
  image-6 (~48%) — photos where the page doesn't fill the frame or is tilted.
  Next lever: auto-crop to the page (plan step 2).
- **Redaction affects scores**: white boxes on grayish paper are themselves
  sharp rectangles (image-1: 27.7% → 15.0% when filled with the paper colour
  instead). Prefer paper-coloured fill.

### Per image (CER)

| Image | baseline, psm 3, dpi -, thresh 0, fast | baseline, psm 3, dpi 300, thresh 2, fast | baseline, psm 6, dpi -, thresh 0, best | v2, psm 3, dpi 300, thresh 0, fast | v2, psm 4, dpi 300, thresh 0, fast | v2, psm 3, dpi 300, thresh 0, best |
| --- | --- | --- | --- | --- | --- | --- |
| image-1 | 14.4% | 1.2% | 15.0% | 1.7% | 1.7% | 1.4% |
| image-10 | 5.2% | 6.2% | 4.4% | 6.0% | 6.4% | 3.7% |
| image-2 | 6.3% | 5.5% | 7.5% | 6.5% | 6.4% | 7.1% |
| image-3 | 71.4% | 65.6% | 102.8% | 67.4% | 89.8% | 66.7% |
| image-4 | 60.7% | 52.9% | 58.0% | 83.2% | 75.9% | 83.4% |
| image-5 | 97.3% | 99.5% | 47.2% | 19.5% | 22.0% | 19.4% |
| image-6 | 39.5% | 46.0% | 61.0% | 50.2% | 47.5% | 51.1% |
| image-8 | 12.7% | 7.7% | 11.1% | 10.1% | 7.4% | 9.5% |
| image-9 | 70.6% | 54.5% | 62.1% | 55.2% | 52.4% | 55.2% |

### All variants

| Variant | CER pooled | CER mean | CER median | WER pooled | CER pooled, POSTPROCESS=1 | s/image |
| --- | --- | --- | --- | --- | --- | --- |
| v2, psm 4, dpi 300, thresh 0, best | 27.5% | 34.2% | 20.3% | 44.5% | 27.5% | 6.2 |
| v2, psm 4, dpi 300, thresh 0, fast | 27.6% | 34.4% | 22.0% | 45.8% | 27.6% | 3.6 |
| v2, psm 4, dpi -, thresh 0, best | 28.2% | 32.2% | 20.5% | 42.1% | 28.2% | 6.0 |
| v2, psm 4, dpi -, thresh 0, fast | 28.2% | 32.2% | 20.5% | 42.4% | 28.2% | 3.3 |
| v2, psm 3, dpi 300, thresh 0, best | 28.8% | 33.1% | 19.4% | 44.7% | 28.8% | 6.0 |
| v2, psm 6, dpi -, thresh 0, best | 29.1% | 36.6% | 26.1% | 63.1% | 29.1% | 7.3 |
| v2, psm 6, dpi 300, thresh 0, best | 29.1% | 36.6% | 26.1% | 63.1% | 29.1% | 7.1 |
| v2, psm 3, dpi 300, thresh 0, fast | 29.2% | 33.3% | 19.5% | 46.4% | 29.2% | 3.5 |
| v2, psm 3, dpi -, thresh 0, best | 29.5% | 36.6% | 19.2% | 41.8% | 29.5% | 5.6 |
| v2, psm 3, dpi -, thresh 0, fast | 29.8% | 36.9% | 18.7% | 43.0% | 29.8% | 3.5 |
| v2, psm 6, dpi -, thresh 0, fast | 30.1% | 38.0% | 25.4% | 65.7% | 30.1% | 3.9 |
| v2, psm 6, dpi 300, thresh 0, fast | 30.1% | 38.0% | 25.4% | 65.7% | 30.1% | 3.8 |
| baseline, psm 3, dpi 300, thresh 2, fast | 31.3% | 37.7% | 46.0% | 51.4% | 31.3% | 3.5 |
| baseline, psm 6, dpi -, thresh 0, best | 31.4% | 41.0% | 47.2% | 61.4% | 31.5% | 6.9 |
| baseline, psm 6, dpi 300, thresh 0, best | 31.4% | 41.0% | 47.2% | 61.4% | 31.5% | 7.1 |
| baseline, psm 3, dpi 300, thresh 2, best | 31.6% | 37.5% | 42.7% | 50.3% | 31.6% | 5.8 |
| baseline, psm 6, dpi -, thresh 0, fast | 31.7% | 41.4% | 53.5% | 63.6% | 31.7% | 3.8 |
| baseline, psm 6, dpi 300, thresh 0, fast | 31.7% | 41.4% | 53.5% | 63.6% | 31.7% | 3.8 |
| baseline, psm 6, dpi -, thresh 2, fast | 32.0% | 41.5% | 48.8% | 64.5% | 32.0% | 3.9 |
| v2, psm 6, dpi -, thresh 2, fast | 32.1% | 40.4% | 42.3% | 70.0% | 32.1% | 3.9 |
| baseline, psm 4, dpi -, thresh 2, fast | 32.2% | 39.5% | 44.8% | 53.7% | 32.2% | 3.5 |
| v2, psm 6, dpi -, thresh 2, best | 32.3% | 41.1% | 44.5% | 69.5% | 32.3% | 7.2 |
| baseline, psm 4, dpi -, thresh 2, best | 32.4% | 39.5% | 44.0% | 53.6% | 32.4% | 6.1 |
| baseline, psm 6, dpi -, thresh 2, best | 32.5% | 42.3% | 48.8% | 63.3% | 32.5% | 7.4 |
| baseline, psm 6, dpi 300, thresh 2, fast | 32.6% | 40.8% | 45.1% | 62.4% | 32.6% | 3.9 |
| v2, psm 4, dpi -, thresh 2, fast | 32.8% | 38.1% | 48.1% | 47.6% | 32.8% | 3.4 |
| baseline, psm 6, dpi 300, thresh 2, best | 33.1% | 41.4% | 44.5% | 61.2% | 33.1% | 6.9 |
| v2, psm 4, dpi -, thresh 2, best | 33.2% | 38.8% | 49.2% | 46.7% | 33.2% | 5.8 |
| baseline, psm 3, dpi -, thresh 2, fast | 33.5% | 40.4% | 46.3% | 53.1% | 33.5% | 3.4 |
| v2, psm 4, dpi 300, thresh 2, best | 33.5% | 40.7% | 44.3% | 49.0% | 33.5% | 5.5 |
| v2, psm 3, dpi -, thresh 2, fast | 33.5% | 43.1% | 48.0% | 50.4% | 33.5% | 3.4 |
| v2, psm 4, dpi 300, thresh 2, fast | 33.6% | 40.8% | 46.7% | 49.8% | 33.6% | 3.4 |
| baseline, psm 4, dpi -, thresh 0, best | 33.9% | 39.8% | 38.5% | 49.7% | 33.9% | 5.6 |
| baseline, psm 4, dpi 300, thresh 2, fast | 33.9% | 40.5% | 46.7% | 55.1% | 34.0% | 3.6 |
| baseline, psm 4, dpi 300, thresh 2, best | 34.0% | 40.5% | 42.7% | 54.4% | 34.0% | 6.2 |
| baseline, psm 3, dpi -, thresh 2, best | 34.0% | 41.0% | 47.6% | 52.7% | 34.0% | 5.8 |
| baseline, psm 4, dpi 300, thresh 0, fast | 34.0% | 39.9% | 40.8% | 51.7% | 34.0% | 3.4 |
| v2, psm 3, dpi -, thresh 2, best | 34.1% | 43.4% | 50.8% | 50.6% | 34.1% | 5.9 |
| baseline, psm 4, dpi 300, thresh 0, best | 34.1% | 39.9% | 41.9% | 50.3% | 34.1% | 5.6 |
| v2, psm 3, dpi 300, thresh 2, fast | 34.1% | 41.6% | 51.6% | 49.1% | 34.1% | 3.3 |
| baseline, psm 4, dpi -, thresh 0, fast | 34.2% | 39.9% | 38.1% | 52.1% | 34.2% | 3.3 |
| v2, psm 3, dpi 300, thresh 2, best | 34.3% | 41.8% | 51.0% | 48.7% | 34.3% | 5.5 |
| v2, psm 6, dpi 300, thresh 2, best | 34.6% | 42.9% | 63.2% | 67.8% | 34.6% | 5.7 |
| v2, psm 6, dpi 300, thresh 2, fast | 34.9% | 42.9% | 64.0% | 69.6% | 34.9% | 3.6 |
| baseline, psm 3, dpi 300, thresh 0, best | 35.0% | 40.5% | 39.8% | 50.2% | 35.0% | 5.5 |
| baseline, psm 3, dpi 300, thresh 0, fast | 35.1% | 40.7% | 40.3% | 52.3% | 35.1% | 3.3 |
| baseline, psm 3, dpi -, thresh 0, best | 36.6% | 41.8% | 39.5% | 52.1% | 36.6% | 5.6 |
| baseline, psm 3, dpi -, thresh 0, fast (baseline) | 36.7% | 42.0% | 39.5% | 54.2% | 36.7% | 3.6 |
