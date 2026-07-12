import unittest

from economy.amounts import AmountParseError, allocate_basis_points, format_economy_amount, parse_economy_amount


class EconomyAmountTests(unittest.TestCase):
    def test_accepted_formats(self):
        cases = {
            "10000": 10000,
            "10.000": 10000,
            "10k": 10000,
            "500k": 500000,
            "1m": 1000000,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_economy_amount(raw), expected)
        self.assertEqual(parse_economy_amount("all", balance=9000, allow_all=True), 9000)
        self.assertEqual(parse_economy_amount("half", balance=9001, allow_half=True), 4500)

    def test_rejected_formats(self):
        values = [None, True, False, "", "0", "-1", "+1", "1.0", "1,000", "1e6",
                  "NaN", "Infinity", "10 000", "1.00.000", 1.5]
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(AmountParseError):
                    parse_economy_amount(value)

    def test_format_and_exact_allocation(self):
        self.assertEqual(format_economy_amount(1_250_000, "ETM"), "1.250.000 ETM")
        result = allocate_basis_points(101, (("a", 8000), ("b", 1000), ("c", 1000)))
        self.assertEqual(sum(value for _, value in result), 101)
        self.assertEqual(result, [("a", 80), ("b", 10), ("c", 11)])


if __name__ == "__main__":
    unittest.main()
