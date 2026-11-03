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
