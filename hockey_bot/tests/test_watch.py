from hockeybot.captions import build_context, render_caption
from hockeybot.db import Database
from hockeybot.templates_lib import builtin, demo_card, demo_context, template_body_ok
from hockeybot.watch import watch_action


def test_watch_action() -> None:
    assert watch_action(None, True) == "ready"
    assert watch_action(None, False) == "wait"
    assert watch_action("Матч ещё не начался: Авангард — ЦСКА, 8 ноября.", None) == "wait"
    assert watch_action("Сайт КХЛ сейчас не отвечает. Попробуй ещё раз через минуту.", None) == "wait"
    assert watch_action("КХЛ отдала протокол в неожиданном виде. Попробуй ещё раз.", None) == "wait"
    assert watch_action("Напиши два клуба и дату: Авангард ЦСКА 5 ноября 2026", None) == "drop"


def test_result_template_is_saved_and_watch_is_deduped(tmp_path) -> None:
    db = Database(tmp_path / "bot.sqlite")
    assert template_body_ok("просто текст без полей")
    saved = db.save_result_template(7, "{home} {score} {away}")
    assert saved.name == "Итоги матча"
    assert db.settings(7).default_template == saved.id
    updated = db.save_result_template(7, "{home}\n{goals_block}\n{url}")
    assert updated.id == saved.id
    assert updated.body.startswith("{home}")

    watch, created = db.add_watch(7, 7, "Авангард  ЦСКА 5 ноября 2026")
    assert created
    again, created_again = db.add_watch(7, 7, "Авангард ЦСКА 5 ноября 2026")
    assert again.id == watch.id
    assert created_again is False
    assert len(db.pending_watches()) == 1
    db.finish_query(7, "Авангард ЦСКА 5 ноября 2026")
    assert db.pending_watches() == []
    fresh, created_fresh = db.add_watch(7, 7, "Авангард ЦСКА 5 ноября 2026")
    assert created_fresh
    assert fresh.id != watch.id
    assert db.stop_watches(7) == 1
    assert db.pending_watches() == []


def test_template_caption_keeps_protocol_link() -> None:
    context = build_context(demo_card())
    context["url"] = "https://www.khl.ru/game/1436/902224/resume/"
    text = render_caption("{home} {score}\n{url}", context)
    assert text == "Салават Юлаев 5:0\nhttps://www.khl.ru/game/1436/902224/resume/"
    assert render_caption("{url}", build_context(demo_card())) == ""
    preview = render_caption(builtin("builtin:result").body, demo_context())
    assert "Салават Юлаев 5:0 Лада" in preview
    assert "http" not in preview
