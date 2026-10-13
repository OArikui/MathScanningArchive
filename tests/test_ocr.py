from __future__ import annotations

import unittest

from matharchive.ocr import OCR_SITES, build_manual_ocr_payload


class ManualOCRTests(unittest.TestCase):
    def test_manual_result_is_serializable_and_marked_unverified(self) -> None:
        result = build_manual_ocr_payload("  \\[x^2+1=0\\]  ", "Pix2Text 多言語デモ")
        self.assertEqual(result["method"], "manual")
        self.assertEqual(result["service"], "Pix2Text 多言語デモ")
        self.assertEqual(result["text"], "\\[x^2+1=0\\]")
        self.assertEqual(result["review_status"], "未確認")

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "空です"):
            build_manual_ocr_payload("   ", "手入力")

    def test_free_web_ocr_sites_are_configured(self) -> None:
        self.assertIn("Pix2Text 多言語デモ", OCR_SITES)
        self.assertTrue(OCR_SITES["Pix2Text 多言語デモ"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
