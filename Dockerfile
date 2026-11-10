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
# Bench dependencies and the RapidOCR experiment's models, baked in so the
# bench runs with no network at all (compose sets network_mode: none).
FROM service AS bench
COPY tests/bench/requirements.txt tests/bench/requirements-rapidocr.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/requirements-rapidocr.txt
# monkt/paddleocr-onnx at a pinned commit, checked by SHA-256 (rapid.py checks again).
ARG PADDLEOCR_ONNX=https://huggingface.co/monkt/paddleocr-onnx/resolve/7b02d0a30a07ba2b92ad1ff5a8941ae2c633de65
ADD --chmod=644 --checksum=sha256:61824840edf6e74581898930b8091b1b2318f4b2705a2e8a40ad3de7ac480133 \
    ${PADDLEOCR_ONNX}/detection/v5/det.onnx /opt/rapidocr/det.onnx
ADD --chmod=644 --checksum=sha256:dc6bf0e855247decce214ba6dae5bc135fa0ad725a5918a7fcfb59fad6c9cdee \
    ${PADDLEOCR_ONNX}/languages/eslav/rec.onnx /opt/rapidocr/rec.onnx
ADD --chmod=644 --checksum=sha256:3e95f1581557162870cacdba5af91a4c6be2890710d395b0c3c7578e7ee5e6eb \
    ${PADDLEOCR_ONNX}/languages/eslav/dict.txt /opt/rapidocr/dict.txt
# RapidOCR's own PP-OCRv5 mobile detector (URL and SHA-256 from rapidocr 3.10.0's default_models.yaml).
ADD --chmod=644 --checksum=sha256:4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae \
    https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx \
    /opt/rapidocr/det_mobile.onnx
ENV RAPIDOCR_MODELS_DIR=/opt/rapidocr
