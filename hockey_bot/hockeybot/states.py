from aiogram.fsm.state import State, StatesGroup


class MatchSG(StatesGroup):
    home = State()
    away = State()
    score = State()
    when = State()
    periods = State()
    goals = State()
    footer = State()
    note = State()
    photo = State()
    quick = State()


class DaySG(StatesGroup):
    date = State()


class ResultSG(StatesGroup):
    template = State()
    query = State()


class PostEditSG(StatesGroup):
    photo = State()


class TemplateSG(StatesGroup):
    name = State()
    kind = State()
    body = State()
    edit_body = State()
    tournament = State()
