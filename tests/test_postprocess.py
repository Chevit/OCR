import os
import unittest
from unittest.mock import AsyncMock, patch

from app import main
from app.main import fix_word, postprocess_text, postprocess_tsv


class FixWordTests(unittest.TestCase):
    def check(self, cases):
        for word, expected in cases.items():
            self.assertEqual(fix_word(word), expected, word)

    def test_medical_terms_stay_as_written(self):
        self.check({
            "SpO2": "SpO2", "CO2": "CO2", "O2": "O2", "HbA1c": "HbA1c",
            "J06.9": "J06.9", "I10": "I10", "O10": "O10",
        })
        self.assertEqual(postprocess_text("Sol. Natrii chloridi"), "Sol. Natrii chloridi")

    def test_cyrillic_lookalikes_in_latin_words(self):
        self.check({
            "СO2": "CO2",  # Cyrillic С
            "Sоl.": "Sol.",  # Cyrillic о
            "Natrіі": "Natrii",  # Cyrillic і
            "(Amоxicillin),": "(Amoxicillin),",
            "В12": "B12",
        })

    def test_latin_lookalikes_in_cyrillic_words(self):
        self.check({"Пaцієнт": "Пацієнт", "хвoрoгo": "хворого", "ОРС": "ОРС"})

    def test_icd10_codes_get_latin_letter_and_digits(self):
        self.check({"К29.7,": "K29.7,", "J45.О": "J45.0", "І10": "I10", "О10": "O10"})

    def test_digits_in_numbers_and_dates(self):
        self.check({"2О24": "2024", "12.О5.2024": "12.05.2024", "l00": "100",
                    "3-го": "3-го", "5мг": "5мг"})

    def test_icd10_in_text_gets_latin_letter(self):
        cases = {
            "( Н66.1)Хронічна": "( H66.1)Хронічна",
            "2,0м(Н90.3)": "2,0м(H90.3)",
            "діагноз К29.7, I10": "діагноз K29.7, I10",
            "А09 В18.2 Е11 М54.5 О80 Р07.3 С50.9 Т14 Х59": "A09 B18.2 E11 M54.5 O80 P07.3 C50.9 T14 X59",
        }
        for text, expected in cases.items():
            self.assertEqual(main.fix_icd10(text), expected, text)

    def test_icd10_space_after_dot_is_joined(self):
        cases = {
            "(Н66. 1)": "(H66.1)",
            "H66. 1 Хронічна": "H66.1 Хронічна",
            "M54. 16": "M54.16",
            "Т12. Дата": "T12. Дата",  # a bare code still gets a Latin letter
        }
        for text, expected in cases.items():
            self.assertEqual(main.fix_icd10(text), expected, text)
        self.assertEqual(postprocess_text("Діагноз: К29. 7, І10"), "Діагноз: K29.7, I10")

    def test_postprocess_keeps_codes_latin_inside_cyrillic_words(self):
        self.assertEqual(postprocess_text("отитом.( Н66. 1)Хронічна 2, 0м(Н90.3)"),
                         "отитом.( H66.1)Хронічна 2, 0м(H90.3)")
        tsv = "5\t1\t1\t1\t1\t1\t10\t5\t40\t20\t91.5\t0м(Н90.3)"
        self.assertTrue(postprocess_tsv(tsv).endswith("\t0м(H90.3)"))

    def test_icd10_fix_leaves_other_words(self):
        for text in (
            "Б12.1",  # not a look-alike letter
            "Н6. 1", "Н666.1", "Н66.123",  # not a code's digits
            "НК66.1", "ХН66", "Н66.1мг", "Н66а",  # part of a longer word
            "12.03. 2024", "С5-С6", "ВІЛ", "Пацієнт", "в/ч А3215",
        ):
            self.assertEqual(main.fix_icd10(text), text, text)

    def test_tsv_fixes_word_text_only(self):
        tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
               "4\t1\t1\t1\t1\t0\t0\t0\t50\t20\t-1\t\n"
               "5\t1\t1\t1\t1\t1\t10\t5\t40\t20\t91.5\tК29.7\n")
        rows = postprocess_tsv(tsv).splitlines()
        self.assertEqual(rows[2], "5\t1\t1\t1\t1\t1\t10\t5\t40\t20\t91.5\tK29.7")
        self.assertEqual(rows[:2], tsv.splitlines()[:2])


class PostprocessSwitchTests(unittest.TestCase):
    def test_ocr_applies_postprocess_only_when_enabled(self):
        from fastapi.testclient import TestClient
        from tests.test_tesseract import fake_process, png_bytes

        for enabled, expected in ((False, "Діагноз К29.7"), (True, "Діагноз K29.7")):
            proc = fake_process(stdout="Діагноз К29.7".encode())
            with patch("app.main.POSTPROCESS", enabled), \
                 patch("app.main.detect_rotation", AsyncMock(return_value=0)), \
                 patch("app.main.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
                response = TestClient(main.app).post(
                    "/ocr", files={"file": ("a.png", png_bytes(), "image/png")})
            self.assertEqual(response.json()["text"], expected)


if __name__ == "__main__":
    unittest.main()


class CriticalTokenTest(unittest.TestCase):
    def test_finds_dates_codes_dosages_numbers(self):
        text = "J06.9 від 12.05.2024, Amoxicillin 500 мг, t 38,5, I10, Пацієнт"
        self.assertEqual(main.CRITICAL.findall(text),
                         ["J06.9", "12.05.2024", "500 мг", "38,5", "I10"])

    def test_word_check_uses_the_same_parts(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "static", "index.html"),
                  encoding="utf-8") as f:
            page = f.read()
        for part in main.CRITICAL_PARTS:
            self.assertIn("String.raw`%s`" % part, page)
