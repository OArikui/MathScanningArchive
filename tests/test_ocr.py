from __future__ import annotations

import base64
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from matharchive.ocr import _prepare_data_uri, recognize_image


class OCRPreparationTests(unittest.TestCase):
    def test_prepares_base64_payload_below_service_limit(self) -> None:
        # A high-entropy synthetic image exercises the resizing/compression fallback.
        width, height = 1800, 1200
        pixels = os.urandom(width * height * 3)
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "scan.png"
            Image.frombytes("RGB", (width, height), pixels).save(image_path)
            data_uri = _prepare_data_uri(image_path)
        self.assertTrue(data_uri.startswith("data:image/jpeg;base64,"))
        encoded = data_uri.split(",", 1)[1]
        self.assertLess(len(encoded), 2_000_000)
        self.assertTrue(base64.b64decode(encoded).startswith(b"\xff\xd8"))

    def test_credentials_are_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "App ID"):
            recognize_image("unused.png", "", "")


if __name__ == "__main__":
    unittest.main()
