from __future__ import annotations

from hockeybot.db import Database
from hockeybot.templates_lib import BUILTINS, PostTemplate, builtin


def all_templates(db: Database, owner_id: int) -> list[PostTemplate]:
    return [*BUILTINS, *db.list_templates(owner_id)]


def resolve_template(db: Database, owner_id: int, template_id: str) -> PostTemplate:
    found = builtin(template_id)
    if found is not None:
        return found
    user_template = db.get_template(owner_id, template_id)
    if user_template is not None:
        return user_template
    return builtin("builtin:result")  # type: ignore[return-value]
