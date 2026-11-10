# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS service

WORKDIR /app

# Pillow needs these system libs to build/run wheels on arm (Raspberry Pi) too.
# tesseract-ocr already pulls in the eng and osd languages.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    tesseract-ocr \
    tesseract-ocr-ukr \
    && rm -rf /var/lib/apt/lists/*

# Slower, usually more accurate models; the UI lets the user pick them.
# Pinned to the tessdata_best 4.1.0 commit and checked by SHA-256.
ADD --chmod=644 --checksum=sha256:1277f6e3b6f707063a92d40e7678e7f57154e8414e328e340be9ee9275eea9c8 \
    https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/e2aad9b983032bb1beff9133104a67cdbb87ca4d/ukr.traineddata \
    /usr/share/tessdata_best/ukr.traineddata
ADD --chmod=644 --checksum=sha256:8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba \
    https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/e2aad9b983032bb1beff9133104a67cdbb87ca4d/eng.traineddata \
    /usr/share/tessdata_best/eng.traineddata

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Recognition benchmark (docker compose run bench ...), never deployed ---
# Bench dependencies only; compose runs it with no network at all
# (network_mode: none), so documents can't leave the machine.
FROM service AS bench
COPY tests/bench/requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt
