# OCR service

Local OCR service with a browser upload page. It runs
[DeepSeek-OCR](https://ollama.com/library/deepseek-ocr) through Ollama and is
configured for a Raspberry Pi 5 with 16 GB RAM.

## Start

```bash
sudo docker compose up -d --build
sudo docker compose exec ollama ollama pull deepseek-ocr:latest
curl http://localhost:8000/health
```

The first OCR request can take several minutes on a CPU-only Pi while the
6.7 GB model loads. Later requests reuse the model in memory.

Open `http://<pi-address>:8000` from a device on the same network. Get the
Pi address with `hostname -I`.

## Use

Upload or paste a PNG, JPG, or WEBP image, choose a mode, and select
**Розпізнати**. The document mode returns Markdown and can switch between a
rendered preview and raw Markdown.

The API uses the same upload flow:

```bash
curl -X POST http://localhost:8000/ocr \
  -F "file=@document.png" \
  -F "mode=document"
```

`POST /ocr` accepts `mode=text|table|figure|document`, `output=json|text`,
`max_megapixels`, and `max_predict`.

## Limits and performance

- Uploads are limited to 20 MB and source images to 20 MP to protect Pi RAM.
- The server reduces images to 1 MP by default.
- `GEN_TIME_LIMIT=600` bounds a recognition run; `REQUEST_TIMEOUT=900` allows
  a slow first token while DeepSeek-OCR is loading.
- For the fastest result, use the **Швидко** profile or crop the image around
  the text.

## Access

The service is intended for a trusted local network. Before exposing it
outside that network, set `API_TOKEN` in `docker-compose.yml` and use a bearer
token for API requests.
