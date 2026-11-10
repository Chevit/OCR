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
6. **Later, gated on the bench**: OpenCV perspective correction (only if tilted/keystoned photos lose meaningfully); RapidOCR + PP-OCRv5 eslav (monkt/paddleocr-onnx, languages/eslav) as a second engine, only if it clearly beats Tesseract at comparable speed.
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
- Waiting on the Pi run: if psm 4 + best ≤ 15 s/image at `--jobs 4`, it
  becomes the default.
- Next: fix the line-pitch misread (image-12), verify on new pages, then
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
- Selection set: `Examples/` (images 1–10; image-7 still has no ground truth). Holdout: `Examples/holdout/` (11–19), reported only for a final choice.

## Open question

Share of handwritten documents — neither Tesseract nor PP-OCR mobile handles handwriting well.
