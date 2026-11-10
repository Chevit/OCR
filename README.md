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

`POST /ocr` accepts `mode=text|table`, `output=json|text|tsv|words`,
`model=fast|best` (Tesseract's fast models, or the slower, usually more accurate
tessdata_best ones from `TESSDATA_BEST_DIR`), and `max_megapixels` (overrides
`TESSERACT_MAX_MEGAPIXELS`). The JSON response is `text`, `mode`, `model` (for
example `tesseract fast (ukr+eng)`), `seconds` and
`filename`. `output=tsv` returns Tesseract's raw TSV, and `output=words` returns
JSON with `tsv`, `image` (the prepared page as a JPEG data URL; TSV positions
are in its pixels) and `seconds`.

The mode selects Tesseract's page segmentation mode (`--psm`): `text` uses 3
(automatic layout) and `table` uses 6 (one block read row by row). If table
rows come out jumbled on your documents, 4 is worth trying in `TESSERACT_PSM`
in `app/main.py`.

## Limits and performance

- Uploads are limited to 20 MB (`MAX_UPLOAD_BYTES`) and source images to 20 MP
  (`MAX_SOURCE_MEGAPIXELS`) to protect Pi RAM.
- Crop the image around the text with **Обрізати й повернути** (Enter applies
  the selection, Esc cancels it).
- Tesseract turns sideways or upside-down photos upright (from EXIF, or with
  Tesseract's orientation check when EXIF is missing), levels text tilted up to
  10°, converts to grayscale, raises
  contrast, and keeps up to 8 MP (about a 300 DPI A4 scan) because it needs
  detail. Images under 4 MP (for example photos compressed by a messenger) are
  enlarged up to 2x, which roughly doubles recognition quality for them.

Tesseract settings (environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `TESSERACT_CMD` | `tesseract` | Tesseract binary |
| `TESSERACT_LANGS` | `ukr+eng` | languages passed to `-l` |
| `TESSERACT_MAX_MEGAPIXELS` | `8` | largest image size sent to Tesseract |
| `TESSERACT_TIMEOUT` | `120` | seconds before a run is stopped (504) |
| `OCR_CONCURRENCY` | `4` | recognitions running at once; extra requests wait their turn. Each Tesseract is limited to 1 CPU thread (`OMP_THREAD_LIMIT=1`) |
| `PREPROCESS` | `baseline` | image preparation: `baseline`, or `v2`, which also evens out shadows and uneven light and sizes the page so text is about 30 px high (instead of by megapixels) |
| `TESSDATA_BEST_DIR` | `/usr/share/tessdata_best` | tessdata_best models for `model=best` (the Docker image downloads them) |

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
