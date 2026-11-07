from __future__ import annotations

from hockeybot.db import Database
from hockeybot.templates_lib import BUILTINS, PostTemplate, builtin


def all_templates(db: Database, owner_id: int) -> list[PostTemplate]:
    return [*BUILTINS, *db.list_templates(owner_id)]


def active_result_template(db: Database, owner_id: int) -> PostTemplate:
    current = resolve_template(db, owner_id, db.settings(owner_id).default_template)
    if current.kind == "result":
        return current
    own = [item for item in db.list_templates(owner_id) if item.kind == "result"]
    if own:
        return own[-1]
    return resolve_template(db, owner_id, "builtin:result")


def resolve_template(db: Database, owner_id: int, template_id: str) -> PostTemplate:
    found = builtin(template_id)
    if found is not None:
        return found
    user_template = db.get_template(owner_id, template_id)
    if user_template is not None:
        return user_template
    return builtin("builtin:result")  # type: ignore[return-value]
