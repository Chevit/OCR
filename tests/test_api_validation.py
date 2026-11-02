import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app, downscale_image


class OcrValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_rejects_non_positive_image_limit_before_calling_ollama(self):
        response = self.client.post(
            "/ocr",
            data={"max_megapixels": "-1"},
            files={"file": ("sample.png", b"not examined", "image/png")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "max_megapixels must be greater than 0")

    def test_rejects_oversized_image_before_decoding_it(self):
        image = Mock()
        image.size = (5_000, 5_000)

        with patch("app.main.Image.open", return_value=image):
            with self.assertRaisesRegex(HTTPException, "at most"):
                downscale_image(b"header only", 1)

        image.load.assert_not_called()
