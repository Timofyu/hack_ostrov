from __future__ import annotations

import io
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, UnidentifiedImageError

_MAX_BYTES = 8_000_000
# Нижняя плашка трансляции: счёт, вратари, логотипы. На превью её закрывает наш текст.
_BROADCAST_BAR = 0.16


def download_match_photo(url: str, dest: Path) -> Path | None:
    if not url.startswith("https://"):
        return None
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "hockey-poster-bot/1.0", "Accept": "image/*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read(_MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if len(payload) < 1000 or len(payload) > _MAX_BYTES:
        return None
    try:
        image = Image.open(io.BytesIO(payload))
        image.load()
    except (UnidentifiedImageError, OSError):
        return None
    frame = _without_broadcast_bar(image).convert("RGB")
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = dest.with_suffix(".jpg")
    frame.save(target, "JPEG", quality=90)
    return target


def _without_broadcast_bar(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width < 32 or height < 32:
        return image
    if width / height < 1.5:
        return image
    keep = int(height * (1 - _BROADCAST_BAR))
    if keep < 32 or keep >= height:
        return image
    return image.crop((0, 0, width, keep))
