"""Free, manual OCR workflow helpers for MathArchive.

The application does not submit user images to an OCR provider. Users may open a
free web demo, upload a chosen image themselves, and paste the result back into the app.
"""
from __future__ import annotations

from typing import Any

OCR_SITES: dict[str, str] = {
    "Pix2Text 多言語デモ": "https://huggingface.co/spaces/breezedeus/Pix2Text-Demo",
    "Pix2Text オンライン版（英語・簡体字中国語向け）": "https://p2t.breezedeus.com/",
}


def build_manual_ocr_payload(recognized_text: str, service_name: str) -> dict[str, Any]:
    """Return a JSON-serializable audit record for text pasted by the user."""
    text = recognized_text.strip()
    if not text:
        raise ValueError("OCR 結果が空です。認識結果を貼り付けてください。")
    service = service_name.strip() or "手入力"
    return {
        "method": "manual",
        "service": service,
        "text": text,
        "review_status": "未確認",
    }
