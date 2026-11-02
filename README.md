# OCR service

Local OCR service with a browser upload page, configured for a Raspberry Pi 5
with 16 GB RAM. It has two engines:

| Engine | UI label | Speed on the Pi | Best for |
| --- | --- | --- | --- |
| `tesseract` | Швидко (Tesseract) | seconds | clean printed documents in Ukrainian and English |
| `deepseek` | Точно (DeepSeek) | a minute or more | difficult photos, handwriting-like or mixed layouts, Markdown output |

[Tesseract](https://github.com/tesseract-ocr/tesseract) runs inside the service
container. [DeepSeek-OCR](https://ollama.com/library/deepseek-ocr) runs through
Ollama. Try Tesseract first; switch to DeepSeek when the text comes out wrong.

## Start

```bash
sudo docker compose up -d --build
sudo docker compose exec ollama ollama pull deepseek-ocr:latest
curl http://localhost:8000/health
sudo docker compose exec ocr tesseract --list-langs   # must list eng and ukr
```

`/health` returns 503 when Ollama is unreachable, but its `tesseract` block
(`available`, `version`, `langs`, `missing_langs`) shows whether the Tesseract
engine still works.

The first OCR request can take several minutes on a CPU-only Pi while the
6.7 GB model loads. Later requests reuse the model in memory.

Open `http://<pi-address>:8000` from a device on the same network. Get the
Pi address with `hostname -I`.

## Use

Upload or paste a PNG, JPG, or WEBP image, choose an engine and a mode, and
select **Розпізнати**. The UI defaults to Tesseract and remembers the last
engine. With DeepSeek, the document mode returns Markdown and can switch between
a rendered preview and raw Markdown. Tesseract always returns plain text.

The API uses the same upload flow:

```bash
curl -X POST http://localhost:8000/ocr \
  -F "file=@document.png" \
  -F "mode=document" \
  -F "engine=tesseract"
```

`POST /ocr` accepts `mode=text|table|figure|document`, `output=json|text`,
`engine=deepseek|tesseract` (default `deepseek`), `max_megapixels`, and
`max_predict`. `max_predict` applies to DeepSeek only. For Tesseract,
`max_megapixels` overrides `TESSERACT_MAX_MEGAPIXELS`. The JSON response
includes `engine` and `model` (for example `tesseract (ukr+eng)`).

For Tesseract, the mode selects the page segmentation mode (`--psm`): `text`
and `document` use 3 (automatic layout), `table` uses 6 (one block read row by
row), and `figure` uses 11 (sparse text). If table rows come out jumbled on
your documents, 4 is worth trying in `TESSERACT_PSM` in `app/main.py`.

## Limits and performance

- Uploads are limited to 20 MB and source images to 20 MP to protect Pi RAM.
- The server reduces images to 1 MP by default.
- `GEN_TIME_LIMIT=600` bounds a recognition run; `REQUEST_TIMEOUT=900` allows
  a slow first token while DeepSeek-OCR is loading.
- For the fastest DeepSeek result, use the **Швидко** profile or crop the
  image around the text.
- Tesseract straightens rotated phone photos, converts to grayscale, raises
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
