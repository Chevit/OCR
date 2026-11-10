import asyncio
import io
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image

from app import main
from app.main import mean_word_confidence


def tsv_with_confs(*confs):
    rows = ["level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"]
    rows.append("4\t1\t1\t1\t1\t0\t0\t0\t9\t9\t-1\t")
    rows += [f"5\t1\t1\t1\t1\t{i}\t0\t0\t9\t9\t{c}\tw" for i, c in enumerate(confs)]
    return ("\n".join(rows) + "\n").encode()


class UpsideDownCheckTests(unittest.TestCase):
    def png(self):
        buf = io.BytesIO()
        page = Image.new("L", (300, 200), 255)
        page.paste(0, (10, 10, 60, 40))  # a mark in one corner, so a flip shows
        page.save(buf, format="PNG")
        return buf.getvalue()

    def test_mean_confidence_ignores_non_words(self):
        self.assertEqual(mean_word_confidence(tsv_with_confs(90, 70).decode()), 80)
        self.assertEqual(mean_word_confidence(tsv_with_confs().decode()), 0)

    def upright(self, as_is, flipped):
        reads = AsyncMock(side_effect=[tsv_with_confs(*as_is), tsv_with_confs(*flipped)])
        with patch("app.main.detect_rotation", AsyncMock(return_value=180)), \
             patch("app.main.run_tesseract", reads):
            page = self.png()
            return page, asyncio.run(main.make_upright(page)), reads

    def test_keeps_page_when_it_reads_better_as_is(self):
        page, result, reads = self.upright(as_is=(90, 88), flipped=(30,))
        self.assertEqual(result, page)
        self.assertEqual(reads.await_count, 2)

    def test_flips_page_when_it_reads_better_flipped(self):
        page, result, _ = self.upright(as_is=(20, 35), flipped=(91,))
        self.assertNotEqual(result, page)

    def test_other_turns_are_trusted_without_extra_reads(self):
        reads = AsyncMock()
        with patch("app.main.detect_rotation", AsyncMock(return_value=90)), \
             patch("app.main.run_tesseract", reads):
            page = self.png()
            turned = asyncio.run(main.make_upright(page))
        width, height = Image.open(io.BytesIO(turned)).size
        self.assertLess(width, height)  # turned sideways (then levelled)
        reads.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
