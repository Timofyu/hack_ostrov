from __future__ import annotations

import asyncio
import time

from hockeybot.captions import build_context, render_caption
from hockeybot.catalog import active_result_template
from hockeybot.db import Database
from hockeybot.khl import ImportedMatch
from hockeybot.photos import download_match_photo
from hockeybot.poster import render_poster
from hockeybot.social import find_social_photos


async def compose_result(
    imported: ImportedMatch,
    user_id: int,
    db: Database,
    chrome_path: str | None,
) -> dict:
    card = imported.card
    folder = db.path.parent / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"khl-{user_id}-{int(time.time())}.jpg"
    social_urls: list[str] = []
    if imported.played_at is not None:
        social_urls = await asyncio.to_thread(find_social_photos, card.home, card.away, imported.played_at)
    saved = None
    for photo_url in social_urls:
        saved = await asyncio.to_thread(download_match_photo, photo_url, target, False)
        if saved is not None:
            break
    if saved is None and imported.photo_url:
        saved = await asyncio.to_thread(download_match_photo, imported.photo_url, target, True)
    if saved is not None:
        card.photo_path = str(saved)

    template = active_result_template(db, user_id)
    context = build_context(card)
    context["url"] = imported.url or ""
    caption = render_caption(template.body, context) or f"{card.home.name} — {card.away.name}"

    renders = db.path.parent / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    dest = renders / f"{user_id}-{int(time.time())}.png"
    await asyncio.to_thread(render_poster, card, dest, chrome_path)
    return {
        "path": str(dest),
        "caption": caption,
        "kind": "result",
        "context": context,
        "template_id": template.id,
        "card": card.to_dict(),
    }
