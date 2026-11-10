from __future__ import annotations

import shutil
from pathlib import Path

from hockeybot.teams import normalize_name

LOGO_DIR = Path(__file__).resolve().parent / "assets" / "logos"


def logo_file(name: str) -> str:
    if not name:
        return ""
    filename = normalize_name(name).replace(" ", "_") + ".png"
    if (LOGO_DIR / filename).is_file():
        return filename
    return ""


def stage_logos(tmp: Path, view: dict) -> None:
    names: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key.endswith("logo") and isinstance(value, str) and value.endswith(".png"):
                    names.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(view)
    if not names:
        return
    folder = tmp / "logos"
    folder.mkdir(exist_ok=True)
    for name in dict.fromkeys(names):
        source = LOGO_DIR / name
        target = folder / name
        if source.is_file() and not target.exists():
            shutil.copy(source, target)
