import unittest

from tests.bench import bench


class PositionalCriticalTests(unittest.TestCase):
    def read(self, truth, text):
        return bench.critical_read(" ".join(truth.split()), " ".join(text.split()))

    def test_date_in_its_place_counts(self):
        self.assertEqual(self.read("Дата 12.03.2024 підпис", "Дата 12.03.2024, підпис")[:2], [1, 1])

    def test_correct_date_in_the_wrong_place_does_not_count(self):
        truth = "Народився 01.02.1990 оглянутий 12.03.2024 лікар"
        text = "Народився 12.03.2024 оглянутий 01.О2.1990 лікар"  # dates swapped, one misread
        self.assertEqual(self.read(truth, text)[:2], [0, 2])

    def test_misread_date_does_not_count(self):
        self.assertEqual(self.read("Дата 12.03.2024", "Дата 12.08.2024")[:2], [0, 1])

    def test_dosage_split_differently_still_counts(self):
        self.assertEqual(self.read("приймати 5 мг двічі", "приймати 5мг двічі")[:2], [1, 1])

    def test_one_character_tokens_are_split_out(self):
        found, truth, found2, truth2 = self.read("пункт 3 доза 12,5", "пункт 3 доза 12,5")
        self.assertEqual((found, truth, found2, truth2), (2, 2, 1, 1))

    def test_score_keeps_the_order_free_count_separately(self):
        s = bench.score("а 12.03.2024 б 01.02.1990", "а 01.02.1990 б 12.03.2024")
        self.assertEqual((s["critical_found"], s["critical_bag_found"]), (0, 2))


if __name__ == "__main__":
    unittest.main()
