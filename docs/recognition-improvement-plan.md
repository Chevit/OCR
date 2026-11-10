# OCR recognition improvement plan (review 2026-11-10)

## Current pipeline (app/main.py)

EXIF transpose → flatten alpha → grayscale + global autocontrast → invert if dark → resize by megapixels (≤8 MP, ≤2x upscale below 4 MP) → skew search ±10° → OSD rotation → tesseract (ukr+eng, psm 3 text / 6 table, fast|best).

## Gaps

1. No way to measure accuracy (no ground-truth set, no CER/WER).
2. Phone photos: no shadow/uneven-light removal, no perspective (keystone) correction, global contrast only.
3. Scale chosen by megapixels, not by text height (Tesseract LSTM works best at ~25–35 px cap height).
4. ukr+eng produces mixed-script words (Latin o/a/e/i/c/p/x inside Cyrillic words) — breaks search/copy into records system.
5. Table mode = psm 6 on the whole page; no cell structure.
6. No domain vocabulary (diagnoses, drugs, ICD-10 codes, dates).
7. Page not filling the frame (phone-UI margins in screenshots, dark desk/table around a photographed page) misleads every step before recognition: the dark-theme check inverts the whole image, OSD confidently flips upright pages 180°, the skew search hits its ±10° limit, and Tesseract layout analysis drops text next to large dark blocks. Today only the manual crop in the UI fixes it.

## Plan (priority order)

1. **P0 Benchmark** — `python -m tests.bench.bench Examples` (CER/WER/s per variant: preprocess baseline|v2, psm 3/4/6, `--dpi 300`, `thresholding_method` 0/2, model fast/best). Every change below must beat the baseline on it. Record results in tests/bench/RESULTS.md.
2. **P1 Auto-crop to the page** (Pillow only), first step after grayscale: find the bright page region (rows/columns that are mostly light) and crop to its bounding box with a small margin. Then, on the cropped page only:

   - decide "dark theme" (invert) — a dark desk around a page must not trigger it;
   - run the skew search and OSD;
   - if OSD still misfires, require higher confidence for a 180° turn (a wrong flip destroys the whole result; upright is the common case).

   A tilted page keeps dark corners after an axis-aligned crop — that is the case where OpenCV perspective correction may earn its place; the bench decides.
3. **P1 Preprocessing v2** (Pillow only, `PREPROCESS=baseline|v2`):

   - background normalization: background = MaxFilter + GaussianBlur on a downscaled copy, upscaled back; divide with ImageMath (float);
   - scale by text height: line pitch from the row profile of a ~1500 px levelled copy (autocorrelation peak; pitch ≈ 1.5–2x glyph height), target ~30 px glyph height within the existing limits, at most 2x down; fall back to megapixels when no clear pitch.
4. **P1 Post-processing** (`POSTPROCESS=1`): per-word homoglyph normalization by the dominant unambiguous script; digit fixes (O→0, З→3, l/I→1) in numbers, dates and ICD-10 codes, only when real digits outnumber look-alikes (so "O2"/"CO2" stay). Apply to text and to TSV words (word check keeps boxes).
5. **P2 Table mode as TSV**: build rows/cells from Tesseract word boxes (block/par/line ids for rows, gaps for cells, overlapping x-intervals across rows for columns). Visible with output "Текст"; word check still shows plain lines.
6. **Later, gated on the bench**: OpenCV perspective correction (only if tilted/keystoned photos lose meaningfully); RapidOCR + PP-OCRv5 eslav (monkt/paddleocr-onnx, languages/eslav) as a second engine, only if it clearly beats Tesseract at comparable speed — closed 2026-11-10 (too slow and too large on the Pi, RESULTS.md (8)).
7. **P3** Spell suggestions in word check: hunspell + dict_uk for low-confidence words. Tesseract `--user-words`: skipped (little effect on LSTM).

## Status (2026-11-10)

Results: [tests/bench/RESULTS.md](../tests/bench/RESULTS.md).

- Done: bench harness (CER/WER, word recall/precision/F1, critical tokens;
  `--adaptive`, `--noise` sweeps; Pi run inside the service image);
  `PREPROCESS=v2` as default (baseline path kept); 180° answers checked by
  reading both ways; `POSTPROCESS=1` (off by default); line-pitch and tilt
  fixes; dependency bumps; word check always marks numbers, dates, ICD-10
  codes and dosages.
- Holdout (images 11–19) run once: v2 beats baseline on CER (38.4% → 35.3%
  pooled) and recall, but loses critical tokens (66.4% → 62.2%), all from
  image-12, where line pitch is misread after shadow evening and the page is
  shrunk instead of enlarged. Baseline path stays until that is fixed.
- Tried, not adopted: auto-crop (`PREPROCESS=v3`, branch
  `experiment/autocrop-v3`, a tie with v2); fast-then-best reruns (≤2 points
  of critical tokens for 1.6–2.1x time); dropping low-confidence words and
  tiny blocks (F1 up, but critical tokens down; word check already marks
  those words).
- Pi 5 timings (4 jobs): fast psm 3 9.1 s/image, psm 4 + best 24.6 s/image,
  over the 15 s limit, so fast psm 3 stays the default; best stays a UI
  choice (+4.2 points of critical tokens).
- Line-pitch misread fixed structurally (2026-11-10 (4)): text height may
  shrink a page only above `TESSERACT_MAX_MEGAPIXELS`, otherwise never
  below the megapixel scale. Old holdout is now seen (sanity check only:
  image-12 recovers, v2 fast critical 62.2% → 71.4% vs baseline 66.4%).
- image-17 (baseline 0%): straightening filled corners white on a gray
  photographed page, Tesseract's Otsu then blacked out the whole sheet.
  Fixed: corners get the page's 90th-percentile gray (0 → 1435 characters).
  v2 critical tokens unchanged; baseline loses image-9 tokens (accepted,
  baseline path goes after holdout-2).
- RapidOCR + PP-OCRv5 (bench only, offline image): critical tokens 90.3%
  vs 78.4%, word recall 72.8% vs 83.8% (и for і); on the Pi 116.5 s/image
  vs 10.3 for fast, 1.9 GB RAM per job. Not adopted.
- Critical tokens are now counted in place (positional), not anywhere on
  the page; earlier numbers in this list are the old order-free count.
  Re-scored (RESULTS.md (7)): default 72.2%, psm 4 best 76.7%, RapidOCR
  81.4%; psm 4 now beats psm 3 on critical tokens.
- Hybrid re-read of critical tokens (Tesseract + PP-OCRv5 recognizer):
  +0.3 points positional, not adopted (branch `experiment/hybrid-reread`).
- RapidOCR with the PP-OCRv5 mobile detector (RESULTS.md (8)), last
  engine experiment: 82.6% positional critical vs 72.2%, recall 73.4% vs
  84.3%; on the Pi 38.3 s/image vs 10.4 for fast (+27.9 s, gate ≤ 5 s)
  and 760 MB per job (gate ≤ 500 MB). **Second engine closed**: no
  Tesseract + PP-OCR merge; RapidOCR stays bench-only.
- Detector re-check (RESULTS.md (9)), official PaddlePaddle detectors with
  their own settings, eslav rec: v6 small 84.4% / v6 tiny 83.4% positional
  critical, ~350 MB per job (RAM gate passes), but on the Pi +23.4 to
  +27.3 s/image over fast (gate ≤ 5 s): recognition is ~95% of the time.
  **Second engine stays closed**; only a much faster recognizer (e.g.
  re-reading just uncertain number lines) could reopen it.
- ICD-10 ground truth is Latin everywhere; POSTPROCESS fixes codes'
  letters also inside words and joins "X00. 1" (RESULTS.md (12)): +3.2
  points on crops, +0.2 on pages. POSTPROCESS stays off by default.
- Фрагмент mode (`mode=block`, psm 6): the UI picks it after a crop and
  goes back to Текст when the crop is removed. Crops: CER 11.9% → 9.8%,
  critical 60.2% → 65.9%, same speed on the Pi. fast vs best for
  fragments is decided on holdout-2.
- Holdout-2 layout ready: `Examples/holdout2/pages`, `Examples/holdout2/crops`
  (crops named after their page, `image-20a`).
- Next: holdout-2 (new pages from Che) to confirm the scaling fix, then
  remove the baseline path; table TSV (step 5) not started.

## Findings so far

- Synthetic set: CER 26.4% baseline → 0.7% with v2; Sauvola helps there but **hurts on real pages with v2** (+4–6 points).
- Real set (9 typed pages, white redaction), see tests/bench/RESULTS.md: v2 34.8% → 22.2% pooled CER; `best` models +0.4 points for ~1.8x time; psm 3 ≈ 4; `--dpi 300` no gain; POSTPROCESS ≤0.1 point on CER.
- Black redaction bars broke Tesseract's layout; white boxes on grayish paper also cost some accuracy — prefer paper-coloured fill.
- Rotation misfires came from dark surroundings: OSD flipped upright pages 180° (now checked both ways), and page outlines on a desk won the tilt search (now measured on the page centre only). Baseline still inverts image-5 as a "dark theme" page; v2 recovers it.
- CER punishes reading order; the bench also reports words found in any order.

## Bench data rules

- `Examples/image-N.jpeg` + `Examples/image-N.gt.txt` (UTF-8, exactly what is printed, whitespace and line breaks not scored).
- Redact with paper-coloured (or white) boxes, never black. Keep realistic dark surroundings (phone UI, desks) — those are cases to measure.
- Handwritten pages in a separate folder.
- Selection set: `Examples/` (images 1–10; image-7 still has no ground truth). Old holdout `Examples/holdout/` (11–19) is now seen (image-12 was
  studied); report it only as a sanity check. Holdout-2 (new pages) confirms.

## Open question

Share of handwritten documents — neither Tesseract nor PP-OCR mobile handles handwriting well.
