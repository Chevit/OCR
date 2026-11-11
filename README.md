# OCR service

Local OCR service with a browser upload page, running
[Tesseract](https://github.com/tesseract-ocr/tesseract) (Ukrainian and English)
on a Raspberry Pi 5. Recognition takes seconds.

## Start

```bash
sudo docker compose up -d --build
curl http://localhost:8000/health
```

Step-by-step setup for a Raspberry Pi or a Windows laptop, and removal, is in
[DEPLOY.md](DEPLOY.md).

`/health` returns 503 when Tesseract is missing or lacks a language from
`TESSERACT_LANGS`; its `tesseract` block (`available`, `version`, `langs`,
`missing_langs`) shows which.

Open `http://<pi-address>:8000` from a device on the same network. Get the
Pi address with `hostname -I`.

## Use

Upload or paste a PNG, JPG, or WEBP image, choose **Текст** or **Таблиця**, and
select **Розпізнати**. The result is editable and can be copied or saved as .txt.

The result can also be **Текст з перевіркою слів**: doubtful
words get a dotted underline and likely errors a red highlight. Click a word to
see its confidence and where it is on the page, fix words right in the text,
and use **Наступне слово** to jump between marked words. While checking, the
image area shows the page as Tesseract read it (upright, levelled, grayscale),
so word boxes line up with it exactly.

The API uses the same upload flow:

```bash
curl -X POST http://localhost:8000/ocr \
  -F "file=@document.png" \
  -F "mode=text"
```

`POST /ocr` accepts `mode=text|table|block`, `output=json|text|tsv|words`,
`model=fast|best` (Tesseract's fast models, or the slower, usually more accurate
tessdata_best ones from `TESSDATA_BEST_DIR`), and `max_megapixels` (overrides
`TESSERACT_MAX_MEGAPIXELS`). The JSON response is `text`, `mode`, `model` (for
example `tesseract fast (ukr+eng)`), `seconds` and
`filename`. `output=tsv` returns Tesseract's raw TSV, and `output=words` returns
JSON with `tsv`, `image` (the prepared page as a JPEG data URL; TSV positions
are in its pixels) and `seconds`.

The mode selects Tesseract's page segmentation mode (`--psm`): `text` uses 3
(automatic layout), `table` and `block` use 6 (one block read row by row).
`block` (**Фрагмент** in the UI) is for a cropped part of a page: on crops
psm 6 reads better than 3 (see `tests/bench/RESULTS.md`), on whole pages
worse. The UI switches from Текст to Фрагмент when you crop the image and
back when the crop is removed; you can change it either way. Like every
mode it uses the fast models unless you pick Точні (`model=best`). If table
rows come out jumbled on your documents, 4 is worth trying in `TESSERACT_PSM`
in `app/main.py`.

## Limits and performance

- Uploads are limited to 20 MB (`MAX_UPLOAD_BYTES`) and source images to 20 MP
  (`MAX_SOURCE_MEGAPIXELS`) to protect Pi RAM.
- Crop the image around the text with **Обрізати й повернути** (Enter applies
  the selection, Esc cancels it).
- Tesseract turns sideways or upside-down photos upright (from EXIF, or with
  Tesseract's orientation check when EXIF is missing; when that check says
  upside down, the page is read both ways and the surer reading wins), levels
  text tilted up to 10°, converts to grayscale, evens out shadows and uneven
  light, raises contrast, and resizes the page so text is about 30 px high
  (Tesseract reads that size best): small text, for example in photos
  compressed by a messenger, is enlarged up to 2x, and the result stays within
  8 MP. When the text size can't be measured, images under 4 MP are enlarged
  up to 2x instead.

Tesseract settings (environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `TESSERACT_CMD` | `tesseract` | Tesseract binary |
| `TESSERACT_LANGS` | `ukr+eng` | languages passed to `-l` |
| `TESSERACT_MAX_MEGAPIXELS` | `8` | largest image size sent to Tesseract |
| `TESSERACT_TIMEOUT` | `120` | seconds before a run is stopped (504) |
| `OCR_CONCURRENCY` | `4` | recognitions running at once; extra requests wait their turn. Each Tesseract is limited to 1 CPU thread (`OMP_THREAD_LIMIT=1`) |
| `POSTPROCESS` | `1` | `0` turns it off. `1` fixes Latin/Cyrillic look-alike letters inside words (`Пaцієнт` → `Пацієнт`, `СO2` → `CO2`) and letters read instead of digits in numbers, dates and ICD-10 codes (`К29.7` → `K29.7`, `12.О5.2024` → `12.05.2024`); ICD-10 codes get a Latin letter also when glued to other text (`0м(Н90.3)` → `0м(H90.3)`) and lose a space after the dot (`H66. 1` → `H66.1`, plain-text output only); applies to text and word-check output |
| `TESSDATA_BEST_DIR` | `/usr/share/tessdata_best` | tessdata_best models for `model=best` (the Docker image downloads them) |

## Logs

The service appends to two files in `LOG_DIR` (default `logs/`; Docker
Compose mounts it at `./logs` next to `docker-compose.yml`; an empty value
turns logging off). Each file rotates at 5 MB, keeping 3 old copies. Neither
ever holds recognized text or file names.

- `usage.log`: one tab-separated line per page open or OCR request: time,
  `page` or `ocr`, HTTP status (499 = stopped by the user), client IP.
- `stats.jsonl`: one JSON line per recognition: `time`, `mode`, `model`,
  `output`, `bytes`, `content_type`, `max_megapixels`, `postprocess`, `status`,
  `seconds` (total) and `queue_seconds` (waiting for a free slot), and what the
  preparation decided: `source_format`, `source_size` ([width, height]),
  `inverted` (light text on dark), `skew` (degrees), `line_pitch` (px),
  `scale`, `osd_rotation` (the orientation check's answer) and `rotated` (what
  was applied). Text output adds `chars` and `lines`; `tsv`/`words` output
  adds `words`, `mean_confidence` and `low_confidence_words` (under 60).
  A request that failed partway has only the fields it got to.

```bash
jq -s 'group_by(.mode) | map({mode: .[0].mode, n: length, avg_s: (map(.seconds) | add / length)})' logs/stats.jsonl
```

## Tests

```bash
python -m unittest
```

The test with real Tesseract runs only where Tesseract, its `ukr` language and
a font with Cyrillic are installed (for example on a Mac after
`brew install tesseract tesseract-lang`); elsewhere it is skipped.

## Access

The service is intended for a trusted local network. Before exposing it
outside that network, set `API_TOKEN` in `docker-compose.yml` and use a bearer
token for API requests.
