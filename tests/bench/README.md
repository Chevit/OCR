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

## Data: `Examples/` (never committed)

Real medical documents live in `Examples/` at the repository root, which
`.gitignore` excludes. Never move them anywhere git tracks.

- One image plus a UTF-8 text file with the same name: `image-3.jpeg` and
  `image-3.gt.txt`. Images without a `.gt.txt` are skipped.
- Type exactly what is printed (spelling, case, punctuation, numbers).
  Whitespace and line breaks are not scored.
- Redact with **white** boxes. Black bars break Tesseract's layout analysis
  and drop the text around them, which real uploads don't have.
- Keep realistic dark surroundings (phone UI in screenshots, a desk around a
  photographed page): those are cases to measure.
- Handwritten pages go in a separate folder, `Examples/handwritten/`.

## Holdout

Pick variants on `Examples/` (images 1–10) only. Images 11–19 go in
`Examples/holdout/`; subfolders are not read by default. Run the holdout
only for the final choice, to check it wasn't tuned to the first ten:

```bash
python -m tests.bench.bench Examples/holdout --preprocess v2 --psm 4 --dpi 300 --thresh 0 --model fast
```

## Reading results

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
