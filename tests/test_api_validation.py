import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app, open_image


class OcrValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_rejects_non_positive_image_limit_before_running_ocr(self):
        response = self.client.post(
            "/ocr",
            data={"max_megapixels": "-1"},
            files={"file": ("sample.png", b"not examined", "image/png")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "max_megapixels має бути більше 0")

    def test_rejects_oversized_image_before_decoding_it(self):
        image = Mock()
        image.size = (5_000, 5_000)

        with patch("app.main.Image.open", return_value=image):
            with self.assertRaisesRegex(HTTPException, "не більше"):
                open_image(b"header only")

        image.load.assert_not_called()


class ModelChoiceTests(unittest.TestCase):
    def test_best_models_missing_is_a_clear_error(self):
        with patch("app.main.TESSDATA_BEST_DIR", "/nonexistent/tessdata_best"):
            response = TestClient(app).post(
                "/ocr",
                data={"model": "best"},
                files={"file": ("sample.png", b"not examined", "image/png")},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Точні моделі", response.json()["detail"])

    def test_best_points_tesseract_at_the_best_models(self):
        import asyncio
        from unittest.mock import AsyncMock

        from app.main import run_tesseract

        proc = Mock(returncode=0)
        proc.communicate = AsyncMock(return_value=(b"text", b""))
        for model, expected in (("fast", False), ("best", True)):
            with patch("app.main.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as spawn:
                asyncio.run(run_tesseract(b"png", "text", model=model))
            self.assertEqual("--tessdata-dir" in spawn.call_args.args, expected)


class HealthTests(unittest.TestCase):
    def test_returns_503_when_tesseract_is_unusable(self):
        from unittest.mock import AsyncMock

        status = {"available": False, "version": None, "langs": [], "missing_langs": ["ukr"]}
        with patch("app.main.tesseract_status", AsyncMock(return_value=status)):
            response = TestClient(app).get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "tesseract_unavailable")


class CancelOnDisconnectTests(unittest.TestCase):
    def test_cancels_work_when_browser_disconnects(self):
        import asyncio
        from unittest.mock import AsyncMock

        from app.main import cancel_on_disconnect

        cancelled = []

        async def never_finishes():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        request = Mock(is_disconnected=AsyncMock(return_value=True))
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(cancel_on_disconnect(request, never_finishes()))

        self.assertEqual(ctx.exception.status_code, 499)
        self.assertEqual(cancelled, [True])


class ConcurrencyTests(unittest.TestCase):
    def test_runs_at_most_the_limit_at_once_and_finishes_all(self):
        import asyncio

        from app import main

        running = peak = 0

        async def slow_tesseract(*args):
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.05)
            running -= 1
            return b"text"

        async def go():
            with patch.object(main, "OCR_SLOTS", asyncio.Semaphore(2)), \
                 patch.object(main, "prepare_for_tesseract", return_value=b"png"), \
                 patch.object(main, "detect_rotation", return_value=0), \
                 patch.object(main, "run_tesseract", slow_tesseract):
                return await asyncio.gather(*(main.tesseract_ocr(b"x", "text", 8) for _ in range(6)))

        results = asyncio.run(go())
        self.assertEqual(len(results), 6)
        self.assertEqual(peak, 2)


class LogTests(unittest.TestCase):
    def test_recognition_writes_usage_and_stats_without_text(self):
        import io
        import json
        from unittest.mock import AsyncMock

        from PIL import Image

        png = io.BytesIO()
        Image.new("L", (200, 100), 255).save(png, format="PNG")
        with patch("app.main.run_tesseract", AsyncMock(return_value="Пацієнт Іванов\n".encode())), \
             patch("app.main.detect_rotation", AsyncMock(return_value=0)), \
             patch("app.main.USAGE_LOG") as usage, patch("app.main.STATS_LOG") as stats:
            response = TestClient(app).post(
                "/ocr", files={"file": ("secret-name.png", png.getvalue(), "image/png")})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(usage.info.call_args.args[2:4], ("ocr", 200))
        line = stats.info.call_args.args[0]
        self.assertNotIn("Іванов", line)
        self.assertNotIn("secret-name", line)
        record = json.loads(line)
        self.assertEqual(record["status"], 200)
        self.assertEqual(record["source_size"], [200, 100])
        self.assertEqual(record["rotated"], 0)
        self.assertEqual(record["chars"], len("Пацієнт Іванов"))
        self.assertIn("queue_seconds", record)
