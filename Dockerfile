FROM python:3.11-slim

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
ADD --chmod=644 https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/4.1.0/ukr.traineddata \
    https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/4.1.0/eng.traineddata \
    /usr/share/tessdata_best/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
