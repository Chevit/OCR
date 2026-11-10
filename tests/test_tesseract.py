import asyncio
import base64
import io
import os
import shutil
import subprocess
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app.main import (app, clean_tesseract_text, detect_rotation, find_skew_angle,
                      prepare_for_tesseract)


def png_bytes(size=(200, 100), mode="RGB", color="white"):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format="PNG")
    return buf.getvalue()


def fake_process(stdout=b"", stderr=b"", returncode=0):
    proc = Mock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.wait = AsyncMock()
    proc.returncode = returncode
    return proc


class TesseractEngineTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def post(self, **data):
        # The orientation check is its own tesseract run; tested separately.
        with patch("app.main.detect_rotation", AsyncMock(return_value=0)):
            return self.client.post(
                "/ocr",
                data=data,
                files={"file": ("sample.png", png_bytes(), "image/png")},
            )

    def test_rejects_removed_modes(self):
        response = self.post(mode="document")
        self.assertEqual(response.status_code, 422)

    def test_passes_languages_and_psm_per_mode(self):
        for mode, psm in {"text": "3", "table": "6", "block": "6"}.items():
            proc = fake_process(stdout="Привіт  \n\n\n\n\nHello\f".encode())
            with patch("app.main.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as exec_:
                response = self.post(mode=mode)

            self.assertEqual(response.status_code, 200, response.text)
            args = exec_.call_args.args
            self.assertEqual(args[:3], ("tesseract", "stdin", "stdout"))
            self.assertEqual(args[args.index("-l") + 1], "ukr+eng")
            self.assertEqual(args[args.index("--psm") + 1], psm, mode)
            self.assertIn("preserve_interword_spaces=1", args)
            self.assertTrue(proc.communicate.call_args.args[0].startswith(b"\x89PNG"))

            body = response.json()
            self.assertEqual(body["text"], "Привіт\n\n\nHello")
            self.assertEqual(body["model"], "tesseract fast (ukr+eng)")

    def test_tsv_output_returns_raw_tesseract_file(self):
        body = b"level\tpage_num\n5\t1\n"
        proc = fake_process(stdout=body)
        with patch("app.main.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as exec_:
            response = self.post(output="tsv")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(exec_.call_args.args[-1], "tessedit_create_tsv=1")
        self.assertEqual(response.content, body)
        self.assertTrue(response.headers["content-type"].startswith("text/tab-separated-values"))

    def test_words_output_returns_tsv_and_the_page_it_refers_to(self):
        proc = fake_process(stdout=b"level\tpage_num\n5\t1\n")
        with patch("app.main.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as exec_:
            response = self.post(output="words")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(exec_.call_args.args[-1], "tessedit_create_tsv=1")
        body = response.json()
        self.assertEqual(body["tsv"], "level\tpage_num\n5\t1\n")
        prefix = "data:image/jpeg;base64,"
        self.assertTrue(body["image"].startswith(prefix))
        # Same pixels Tesseract read: the PNG piped to it.
        sent = Image.open(io.BytesIO(proc.communicate.call_args.args[0]))
        page = Image.open(io.BytesIO(base64.b64decode(body["image"][len(prefix):])))
        self.assertEqual(page.size, sent.size)

    def test_pdf_output_is_rejected(self):
        response = self.post(output="pdf")
        self.assertEqual(response.status_code, 422)

    def test_timeout_kills_process_and_returns_504(self):
        async def hang(_):
            await asyncio.sleep(10)

        proc = fake_process()
        proc.communicate = AsyncMock(side_effect=hang)
        with patch("app.main.TESSERACT_TIMEOUT", 0.05), \
             patch("app.main.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            response = self.post()

        self.assertEqual(response.status_code, 504)
        proc.kill.assert_called_once()

    def test_missing_binary_returns_503(self):
        with patch("app.main.asyncio.create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError)):
            response = self.post()
        self.assertEqual(response.status_code, 503)

    def test_failed_run_returns_502_with_stderr(self):
        proc = fake_process(stderr=b"Failed loading language 'ukr'", returncode=1)
        with patch("app.main.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertIn("Failed loading language 'ukr'", response.json()["detail"])

    def test_dark_theme_page_is_inverted_and_not_tilted(self):
        from app.main import prepare_for_tesseract

        page = Image.new("L", (800, 300), 15)
        draw = ImageDraw.Draw(page)
        for y in (100, 150, 200):  # light stripes standing in for text
            draw.rectangle((150, y, 650, y + 12), fill=200)
        buf = io.BytesIO()
        page.save(buf, format="PNG")

        prepared = Image.open(io.BytesIO(prepare_for_tesseract(buf.getvalue(), 8)))
        self.assertGreater(prepared.getpixel((5, 5)), 128)  # background now light
        self.assertEqual(prepared.size[0] / prepared.size[1], 800 / 300)  # not rotated

    def test_finds_tilt_of_rotated_text_rows(self):
        page = Image.new("L", (800, 600), 255)
        draw = ImageDraw.Draw(page)
        for y in range(60, 560, 40):  # stripes standing in for lines of text
            draw.rectangle((80, y, 720, y + 12), fill=0)
        tilted = page.rotate(-4, resample=Image.BICUBIC, fillcolor=255)

        self.assertAlmostEqual(find_skew_angle(tilted), 4, delta=0.3)
        self.assertEqual(find_skew_angle(page), 0)
        self.assertEqual(find_skew_angle(Image.new("L", (400, 300), 255)), 0)

    def test_tilt_ignores_slanted_page_edges_on_a_desk(self):
        # A page photographed at an angle on a dark desk (like a keystoned
        # photo): its outline slants, its text lines are level. Flattening
        # the light (v2) turns the outline into bright/dark bands that used
        # to outvote the text.
        from app.main import flatten_background

        desk = Image.new("L", (1000, 1400), 40)
        draw = ImageDraw.Draw(desk)
        draw.polygon([(140, 20), (980, 160), (900, 1390), (20, 1250)], fill=235)
        for y in range(380, 1030, 45):
            draw.rectangle((300, y, 700, y + 14), fill=0)

        self.assertLess(abs(find_skew_angle(desk)), 1)
        self.assertLess(abs(find_skew_angle(flatten_background(desk))), 1)

    def test_v2_finds_line_pitch_of_tilted_rows(self):
        from app.main import line_pitch

        page = Image.new("L", (2000, 1500), 255)
        draw = ImageDraw.Draw(page)
        for y in range(100, 1400, 70):  # text lines every 70 px
            draw.rectangle((150, y, 1850, y + 30), fill=0)
        tilted = page.rotate(-3, resample=Image.BICUBIC, fillcolor=255)

        self.assertAlmostEqual(line_pitch(tilted, 3), 70, delta=2)
        self.assertIsNone(line_pitch(Image.new("L", (800, 600), 255), 0))

    def test_v2_evens_out_shadows(self):
        from app.main import flatten_background

        light = Image.linear_gradient("L").resize((1200, 900)).point(lambda v: 90 + v * 165 // 255)
        page = light.copy()
        ImageDraw.Draw(page).rectangle((100, 400, 1100, 420), fill=20)  # a line of text
        flat = flatten_background(page)

        lo, hi = flat.crop((0, 0, 1200, 300)).getextrema()  # background only
        self.assertGreater(lo, 230)  # dark corner lifted to near white
        self.assertLess(flat.getpixel((600, 410)), 80)  # text stays dark

    def test_v2_scales_text_to_target_height(self):
        from app.main import prepare_for_tesseract

        page = Image.new("L", (2400, 1800), 255)  # 4.3 MP: baseline keeps the size
        draw = ImageDraw.Draw(page)
        for y in range(100, 1700, 105):  # pitch 105 -> glyphs ~60 px -> half size
            draw.rectangle((150, y, 2250, y + 55), fill=0)
        buf = io.BytesIO()
        page.save(buf, format="PNG")

        size = lambda pp, mp=8: Image.open(io.BytesIO(prepare_for_tesseract(buf.getvalue(), mp, pp))).size
        self.assertEqual(size("baseline"), (2400, 1800))
        # Under max_megapixels text height never shrinks the page...
        self.assertEqual(size("v2"), (2400, 1800))
        # ...over it, it may shrink below the megapixel cap (0.68x here).
        self.assertAlmostEqual(size("v2", 2)[0], 1200, delta=40)

    def test_v2_misread_pitch_harmonic_does_not_shrink_the_page(self):
        # Every 4th line is a full dark line, the rest short and faint: the
        # row profile peaks at 4x the real 26 px pitch (image-12 in the
        # holdout read 114 px instead of 25.6 px and was shrunk to 0.5x).
        from app.main import line_pitch, prepare_for_tesseract

        page = Image.new("L", (1200, 1600), 255)  # 1.9 MP: baseline enlarges it
        draw = ImageDraw.Draw(page)
        for i, y in enumerate(range(80, 1520, 26)):
            if i % 4 == 0:
                draw.rectangle((100, y, 1100, y + 14), fill=0)
            else:
                draw.rectangle((100, y + 5, 400, y + 9), fill=0)
        self.assertGreater(line_pitch(page, 0), 2 * 26)  # the case this guards
        buf = io.BytesIO()
        page.save(buf, format="PNG")

        size = lambda pp: Image.open(io.BytesIO(prepare_for_tesseract(buf.getvalue(), 8, pp))).size
        self.assertGreaterEqual(size("v2")[0], size("baseline")[0])

    def test_orientation_check_trusts_only_confident_answers(self):
        def osd(stdout, returncode=0):
            proc = fake_process(stdout=stdout, returncode=returncode)
            with patch("app.main.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as exec_:
                result = asyncio.run(detect_rotation(b"png"))
            self.assertIn("--psm", exec_.call_args.args)
            return result

        self.assertEqual(osd(b"Rotate: 90\nOrientation confidence: 6.3\n"), 90)
        self.assertEqual(osd(b"Rotate: 180\nOrientation confidence: 0.4\n"), 0)
        self.assertEqual(osd(b"Too few characters. Skipping this page", returncode=1), 0)
        with patch("app.main.asyncio.create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError)):
            self.assertEqual(asyncio.run(detect_rotation(b"png")), 0)

    def test_clean_text_keeps_at_most_two_blank_lines(self):
        self.assertEqual(clean_tesseract_text("a \n\n\nb\n\n\n\n\nc\f"), "a\n\n\nb\n\n\nc")


def _has_ukr():
    if not shutil.which("tesseract"):
        return False
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
    return "ukr" in (out.stdout + out.stderr).split()


CYRILLIC_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]
FONT = next((f for f in CYRILLIC_FONTS if os.path.exists(f)), None)
IMAGE_17 = os.path.join(os.path.dirname(__file__), "..", "Examples", "holdout", "image-17.jpeg")


@unittest.skipUnless(_has_ukr() and FONT, "needs tesseract with 'ukr' and a Cyrillic font")
class TesseractIntegrationTest(unittest.TestCase):
    def test_recognizes_ukrainian(self):
        img = Image.new("RGB", (1400, 300), "white")
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(FONT, 64)
        draw.text((40, 40), "Привіт, лікарю", fill="black", font=font)
        draw.text((40, 160), "Діагноз: бронхіт", fill="black", font=font)
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        response = TestClient(app).post(
            "/ocr",
            files={"file": ("sample.png", buf.getvalue(), "image/png")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Привіт", response.json()["text"])
        self.assertIn("Діагноз", response.json()["text"])

    @unittest.skipUnless(os.path.exists(IMAGE_17), "needs the private bench page Examples/holdout/image-17.jpeg")
    def test_tilted_gray_page_is_not_blacked_out(self):
        # White corners from straightening this gray photographed page made
        # Tesseract's Otsu threshold black out the whole sheet (0 characters).
        # Synthetic gray pages didn't reproduce it, so this uses the real page.
        with open(IMAGE_17, "rb") as f:
            png = prepare_for_tesseract(f.read(), 4.0, "baseline")
        out = subprocess.run(["tesseract", "stdin", "stdout", "-l", "ukr+eng", "--psm", "3"],
                             input=png, capture_output=True, check=True).stdout.decode()
        self.assertGreater(len(out.strip()), 500)


if __name__ == "__main__":
    unittest.main()
