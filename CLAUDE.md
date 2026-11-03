# OCR service

- `python -m unittest` - run tests; the real-Tesseract test is skipped unless `brew install tesseract tesseract-lang` is done
- Runs on a Raspberry Pi 5 via `docker compose`; keep RAM and CPU use low (limits live in `app/main.py`)
- Backend is all in `app/main.py` (FastAPI); the UI is the single file `static/index.html` with Ukrainian labels
- `--tessdata-dir` (used for `model=best`) hides config files from the default tessdata folder, like `tsv`; pass the setting with `-c` instead
- README documents the API params and env vars; update it when you change them
