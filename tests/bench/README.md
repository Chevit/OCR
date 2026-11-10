# Recognition benchmark

Measures how well each Tesseract variant reads real documents: character and
word error rates (CER, WER) against hand-typed text, and seconds per image.
Every recognition change has to beat the current settings here.

```bash
pip install -r tests/bench/requirements.txt
python -m tests.bench.bench                    # reads Examples/
TESSDATA_BEST_DIR=~/tessdata_best python -m tests.bench.bench   # include model=best
python -m tests.bench.bench --psm 4 --model fast                # fewer variants
```

On the Pi (or anywhere with Docker), run it in the `bench` image: the
service image plus the bench packages and RapidOCR models, with no network
(`network_mode: none`), so documents can't leave the machine. Bench
dependencies stay out of the production `requirements.txt` and image.

```bash
sudo docker compose run --build --rm bench python -m tests.bench.bench Examples --jobs 4 ...
```

## Data: `Examples/` (never committed)

Real medical documents live in `Examples/` at the repository root, which
`.gitignore` excludes. Never move them anywhere git tracks.

- One image plus a UTF-8 text file with the same name: `image-3.jpeg` and
  `image-3.gt.txt`. Images without a `.gt.txt` are skipped.
- Type exactly what is printed (spelling, case, punctuation, numbers).
  Whitespace and line breaks are not scored.
- ICD-10 codes always get a **Latin** letter (`H66.1`, `K29.7`, `I10`),
  even on a Ukrainian keyboard: print can't tell Н from H, and the scoring
  compares characters. Check with
  `grep -rnE '(^|[^[:alnum:]])[АВЕКМНОРСТХІ][0-9]{2}([^0-9]|$)' Examples --include='*.gt.txt'`
  (no output = fine). Military unit numbers stay Cyrillic (`в/ч А3215`).
- Redact with **paper-coloured** boxes (white on gray paper costs some
  accuracy). Black bars break Tesseract's layout analysis and drop the text
  around them, which real uploads don't have.
- Keep realistic dark surroundings (phone UI in screenshots, a desk around a
  photographed page): those are cases to measure.
- Handwritten pages go in a separate folder, `Examples/handwritten/`.

## Sets

The bench reads only the folders it is given (no subfolders).

| Folder | What | Use |
| --- | --- | --- |
| `Examples/` | pages 1–10 | selection: pick variants here |
| `Examples/crops/` | crops of pages 1–10 | selection for Фрагмент (`mode=block`) |
| `Examples/holdout/` | pages 11–19 | seen (image-12 was studied): sanity check only |
| `Examples/crops-2/` | crops of pages 11–19 | seen, sanity check only |

Run every set after a recognition change; record the numbers in
`RESULTS.md` with the machine they ran on.

## Regression cases

When a real upload reads badly, it becomes a case:

1. Redact it with **paper-coloured** boxes (pick the colour from the page;
   white boxes on gray paper are sharp edges Tesseract trips on), never
   black.
2. Type its `.gt.txt` (rules above; ICD-10 letters Latin).
3. Put it in the set it belongs to: a whole page in `Examples/`, a cropped
   part in `Examples/crops/`, the next free number (`image-20.jpeg`).
4. Run that set and record its per-image row in `RESULTS.md`, with what was
   wrong. From then on the bench must not get worse on it: a change that
   lowers its CER, recall or critical tokens needs a stated reason.

## Reading results

- **Word recall / precision / F1**: words of the ground truth found in the
  output, and output words that are in the ground truth, in any order.
- **Critical tokens (positional)**: dates, ICD-10 codes, dosages and other
  numbers from the ground truth, share read exactly in their place: output
  words are aligned to ground-truth words, and a token counts only if the
  words aligned to it contain it. Shown with and without `POSTPROCESS=1`
  (the service's default output is the `POSTPROCESS=1` column),
  and for tokens of 2+ characters only (a lone "1" or "3" is easy to hit
  by chance). The old order-free count is kept as "deprecated" for one
  report (2026-11-10 (7) in RESULTS.md); it rewarded a right number
  anywhere on the page.
- `--adaptive` replaces the variant grid with a sweep of "read with fast,
  rerun with best when mean word confidence is below T".
- `--noise` replaces it with a sweep of dropping words below a confidence
  and tiny isolated blocks before output.
- `--model ...,rapidocr` adds RapidOCR (PP-OCRv5 det + eslav rec) on the
  same prepared page, an experiment the service doesn't use. The `bench`
  image has it; outside Docker, `pip install -r
  tests/bench/requirements-rapidocr.txt` and put the model files from the
  Dockerfile into `tests/bench/models/` (hashes are checked). Every run
  prints the peak RAM of one job per model. `rapidocr-v5-mobile`,
  `rapidocr-v6-tiny` and `rapidocr-v6-small` swap in the official
  PaddlePaddle detectors with their own settings (see `rapid.py`).

- **CER pooled**: all character errors / all characters (long pages weigh
  more). **CER mean / median**: of the per-image CERs; the median shows
  whether one bad image drives the result.
- **s/image** includes preparation and the orientation check. It is printed
  with the machine it ran on. Speed only counts when measured on the Pi
  (`--jobs 4` there, like `OCR_CONCURRENCY`); note the machine next to any
  timing you record.
- Results go in `RESULTS.md`.

`synthetic.py` renders a small degraded set for a smoke test when no real
images are at hand; its numbers say little about real pages.
