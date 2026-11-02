# amd64 only — PaddlePaddle has no official ARM64/aarch64 wheel, so this
# image cannot be built or run on Raspberry Pi. See docker-compose.yml,
# where this service sits behind the "precise" profile for that reason.
FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

# OpenCV / Paddle runtime dependencies (headless — no X11 needed, but
# libgl/libglib are still dynamically linked by opencv-python).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
