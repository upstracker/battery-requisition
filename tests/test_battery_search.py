import unittest

from services.battery_search import (
    find_inventory_matches,
    inventory_match_score,
    parse_battery_quick_entry,
)


ITEMS = [
    {
        "id": 1,
        "brand": "FB",
        "item_code": "FB EFB Q100 (D23L) - HIFP",
        "item_name": "FB EFB Q100 (D23L) - HIFP",
        "capacity": "-",
    },
    {
        "id": 2,
        "brand": "AMARON",
        "item_code": "AMARON GO 55D23L",
        "item_name": "แบตเตอรี่ AMARON GO 55D23L",
        "capacity": "-",
    },
    {
        "id": 3,
        "brand": "FB",
        "item_code": "FB N100",
        "item_name": "FB N100",
        "capacity": "100 Ah",
    },
    {
        "id": 4,
        "brand": "ESB",
        "item_code": "ESB N100",
        "item_name": "ESB N100",
        "capacity": "100 Ah",
    },
]


class QuickEntryTests(unittest.TestCase):
    def test_parses_supported_quantity_separators(self):
        self.assertEqual(parse_battery_quick_entry("q100*2"), ("q100", 2, ""))
        self.assertEqual(parse_battery_quick_entry("q100 x 4"), ("q100", 4, ""))
        self.assertEqual(parse_battery_quick_entry("q100×6"), ("q100", 6, ""))
        self.assertEqual(parse_battery_quick_entry("FB N100 3"), ("FB N100", 3, ""))

    def test_keeps_model_when_quantity_is_omitted(self):
        self.assertEqual(parse_battery_quick_entry("55D23L"), ("55D23L", None, ""))
        self.assertEqual(parse_battery_quick_entry("NX120"), ("NX120", None, ""))
        self.assertEqual(parse_battery_quick_entry("MFX60"), ("MFX60", None, ""))

    def test_parses_remark_with_quantity(self):
        self.assertEqual(parse_battery_quick_entry("46b24*2*เทิร์นเก่า"), ("46b24", 2, "เทิร์นเก่า"))
        self.assertEqual(parse_battery_quick_entry("46b24*3 เทิร์น 2 ลูก ขั้ว L"), ("46b24", 3, "เทิร์น 2 ลูก ขั้ว L"))
        self.assertEqual(parse_battery_quick_entry("FB N100 2 แบตใหม่"), ("FB N100", 2, "แบตใหม่"))
        self.assertEqual(parse_battery_quick_entry("q100 x 4 ลูกค้ามารับเอง"), ("q100", 4, "ลูกค้ามารับเอง"))


class BatterySearchTests(unittest.TestCase):
    def test_search_ignores_punctuation_and_spaces(self):
        self.assertIsNotNone(inventory_match_score(ITEMS[1], "55d-23l"))

    def test_brand_and_model_words_can_match_together(self):
        matches = find_inventory_matches(ITEMS, "FB Q100")
        self.assertEqual([item["id"] for _, item in matches], [1])

    def test_exact_model_with_brand_ranks_ahead_of_other_brands(self):
        matches = find_inventory_matches(ITEMS, "FB N100")
        self.assertEqual(matches[0][1]["id"], 3)

    def test_ambiguous_model_returns_all_matching_brands(self):
        matches = find_inventory_matches(ITEMS, "N100")
        self.assertEqual({item["id"] for _, item in matches}, {3, 4})


if __name__ == "__main__":
    unittest.main()
