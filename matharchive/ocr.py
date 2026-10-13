"""Mathpix OCR integration. API credentials are supplied per session or via environment."""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageOps

API_URL = "https://api.mathpix.com/v3/text"


def environment_credentials() -> tuple[str, str]:
    return os.getenv("MATHPIX_APP_ID", "").strip(), os.getenv("MATHPIX_APP_KEY", "").strip()


def _prepare_data_uri(image_path: str | Path) -> str:
    """Create a compact, orientation-correct JPEG data URI under Mathpix's body limits."""
    with Image.open(image_path) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        encoded = b""
        # Keep the base64 payload below 2 MB (the binary image therefore below ~1.4 MB).
        for dimensions, qualities in (
            ((2200, 2200), (88, 80, 72, 64, 56, 48, 40)),
            ((1600, 1600), (72, 64, 56, 48, 40)),
            ((1200, 1200), (64, 56, 48, 40)),
        ):
            image.thumbnail(dimensions, Image.Resampling.LANCZOS)
            for quality in qualities:
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=quality, optimize=True)
                encoded = buffer.getvalue()
                if len(encoded) < 1_400_000:
                    break
            if len(encoded) < 1_400_000:
                break
        if len(encoded) >= 1_400_000:
            raise ValueError("画像を OCR 用サイズに縮小できませんでした。別の画像を使用してください。")
    return "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")


def recognize_image(image_path: str | Path, app_id: str, app_key: str) -> dict[str, Any]:
    if not app_id.strip() or not app_key.strip():
        raise ValueError("Mathpix の App ID と App Key が必要です。")
    image_data = _prepare_data_uri(image_path)
    try:
        response = requests.post(
            API_URL,
            headers={"app_id": app_id.strip(), "app_key": app_key.strip(), "Content-Type": "application/json"},
            json={"src": image_data, "formats": ["text", "data"], "data_options": {"include_latex": True}},
            timeout=(10, 120),
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Mathpix API に接続できませんでした: {exc}") from exc
    if not response.ok:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:500]
        raise RuntimeError(f"Mathpix API エラー ({response.status_code}): {detail}")
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError("OCR サービスから JSON 以外の応答が返されました。") from exc
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    text = payload.get("text", "")
    if not text:
        raise RuntimeError("認識結果が空でした。画像を確認するか、手入力してください。")
    payload["text"] = text
    return payload
