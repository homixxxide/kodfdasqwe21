"""
ARMAGEDON CHAMPIONSHIP — Tournament Match Bot
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Установка: pip install aiogram aiohttp
Запуск: python tournament_match_bot.py
"""

import asyncio
import html
import logging
import random
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramMigrateToChat
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatAction
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile, CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  НАСТРОЙКИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_TOKEN = "8750744135:AAHVYJLZHsDnYCznHKFDy_aQ4z4q1Q-tTMg"
ADMIN_IDS  = {6611491689}   # Telegram ID администраторов
REPORT_CHAT_ID = -1003970043019  # ID закрытого чата для итогов матчей

TOURNAMENT_TZ = ZoneInfo("Europe/Moscow")  # турнирный часовой пояс (МСК)
NOTIFY_BEFORE_MINUTES = 20   # за сколько минут уведомлять
_notified_matches: set = set()  # чтобы не слать дважды

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЛОГИРОВАНИЕ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

if BOT_TOKEN == "ВАШ_ТОКЕН":
    raise SystemExit("⛔  Впиши BOT_TOKEN в начало файла!")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  БАЗА ДАННЫХ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DB   = "tournament_match.db"
_con = sqlite3.connect(DB, check_same_thread=False)
_con.row_factory = sqlite3.Row
_lk  = threading.Lock()

LINE = "▬" * 20


def _exec(sql: str, params=(), commit=False):
    with _lk:
        cur = _con.execute(sql, params)
        if commit:
            _con.commit()
        return cur


def init_db():
    with _lk:
        _con.executescript("""
            -- Команды
            CREATE TABLE IF NOT EXISTS teams (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL UNIQUE,
                password   TEXT NOT NULL,
                captain_id INTEGER,          -- telegram id капитана (после авторизации)
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Матчи сетки
            CREATE TABLE IF NOT EXISTS matches (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                team1_id   INTEGER,           -- NULL = BYE
                team2_id   INTEGER,
                winner_id  INTEGER,
                round      INTEGER NOT NULL,
                match_num  INTEGER NOT NULL,
                match_date TEXT,              -- дата в формате ДД.ММ.ГГГГ
                match_time TEXT,              -- время HH:MM
                status     TEXT DEFAULT 'pending',
                -- pending | notified | lobby_pending | lobby_confirmed
                -- playing | result_pending | done
                lobby_team_id INTEGER,        -- кто создаёт лобби
                bsize      INTEGER NOT NULL DEFAULT 0
            );

            -- Уведомления о скринах
            CREATE TABLE IF NOT EXISTS screenshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id    INTEGER NOT NULL,
                type        TEXT NOT NULL,   -- 'lobby' | 'result'
                file_id     TEXT NOT NULL,
                from_user   INTEGER,
                team_id     INTEGER,
                confirmed   INTEGER DEFAULT 0,
                ts          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Сессии капитанов (авторизованные пользователи)
            CREATE TABLE IF NOT EXISTS captain_sessions (
                user_id  INTEGER PRIMARY KEY,
                team_id  INTEGER NOT NULL,
                ts       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        _con.commit()
    log.info("✅ БД инициализирована")


# ── Teams ────────────────────────────────────
def db_add_team(name: str, password: str) -> bool:
    try:
        _exec("INSERT INTO teams(name, password) VALUES(?,?)",
              (name, password), commit=True)
        return True
    except sqlite3.IntegrityError:
        return False


def db_get_team_by_name(name: str):
    return _exec("SELECT * FROM teams WHERE name=? COLLATE NOCASE",
                 (name,)).fetchone()


def db_get_team(team_id: int):
    return _exec("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()


def db_get_all_teams():
    return _exec("SELECT * FROM teams ORDER BY id").fetchall()


def db_set_captain(team_id: int, user_id: int):
    _exec("UPDATE teams SET captain_id=? WHERE id=?",
          (user_id, team_id), commit=True)
    _exec("""INSERT OR REPLACE INTO captain_sessions(user_id, team_id)
             VALUES(?,?)""", (user_id, team_id), commit=True)


def db_get_captain_team(user_id: int):
    row = _exec("SELECT team_id FROM captain_sessions WHERE user_id=?",
                (user_id,)).fetchone()
    if row:
        return db_get_team(row["team_id"])
    return None


def db_delete_team(team_id: int):
    _exec("DELETE FROM teams WHERE id=?", (team_id,), commit=True)


# ── Matches ──────────────────────────────────
def db_save_bracket(bsize: int, pairs: list):
    with _lk:
        _con.execute("DELETE FROM matches")
        rows = []
        for i, (t1, t2) in enumerate(pairs, 1):
            rows.append((t1, t2, None, 1, i, None, None, 'pending', None, bsize))
        total  = bsize.bit_length()
        cnt    = bsize // 2
        offset = cnt + 1
        for rnd in range(2, total + 1):
            cnt //= 2
            for n in range(offset, offset + cnt):
                rows.append((None, None, None, rnd, n, None, None, 'pending', None, bsize))
            offset += cnt
        _con.executemany(
            """INSERT INTO matches(team1_id,team2_id,winner_id,round,match_num,
               match_date,match_time,status,lobby_team_id,bsize)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            rows
        )
        _con.commit()


def db_get_matches():
    return _exec("SELECT * FROM matches ORDER BY round,match_num").fetchall()


def db_get_match(match_id: int):
    return _exec("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()


def db_update_match(match_id: int, **kwargs):
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [match_id]
    _exec(f"UPDATE matches SET {sets} WHERE id=?", vals, commit=True)


def db_get_team_matches(team_id: int):
    return _exec(
        """SELECT * FROM matches
           WHERE (team1_id=? OR team2_id=?) AND status != 'pending'
           ORDER BY round, match_num""",
        (team_id, team_id)
    ).fetchall()


def db_save_screenshot(match_id: int, stype: str, file_id: str,
                       from_user: int, team_id: int):
    _exec("""INSERT INTO screenshots(match_id,type,file_id,from_user,team_id)
             VALUES(?,?,?,?,?)""",
          (match_id, stype, file_id, from_user, team_id), commit=True)
    return _con.execute("SELECT last_insert_rowid()").fetchone()[0]


def db_confirm_screenshot(scr_id: int):
    _exec("UPDATE screenshots SET confirmed=1 WHERE id=?",
          (scr_id,), commit=True)


def db_get_screenshot(scr_id: int):
    return _exec("SELECT * FROM screenshots WHERE id=?", (scr_id,)).fetchone()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЛОГИКА СЕТКИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _pow2(n: int) -> int:
    s = 1
    while s < n:
        s <<= 1
    return min(s, 64)


def make_bracket(teams: list) -> tuple[int, list]:
    bsize  = _pow2(len(teams))
    seeded = list(teams) + [None] * (bsize - len(teams))
    random.shuffle(seeded)
    pairs  = []
    for i in range(0, bsize, 2):
        a, b = seeded[i], seeded[i + 1]
        pairs.append((
            int(a["id"]) if a else None,
            int(b["id"]) if b else None,
        ))
    return bsize, pairs


_RNAMES = {0: "🏆 Финал", -1: "Полуфинал", -2: "Четвертьфинал"}


def rname(rnd: int, total: int) -> str:
    return _RNAMES.get(rnd - total, f"Раунд {rnd}")


def team_name(tid: Optional[int]) -> str:
    if tid is None:
        return "BYE"
    t = db_get_team(tid)
    return t["name"] if t else f"#{tid}"


def other_team_id(match_row, team_id: int) -> Optional[int]:
    if match_row["team1_id"] == team_id:
        return match_row["team2_id"]
    if match_row["team2_id"] == team_id:
        return match_row["team1_id"]
    return None


async def notify_both_teams(match_row, text: str, reply_markup=None):
    for tid in [match_row["team1_id"], match_row["team2_id"]]:
        t = db_get_team(tid) if tid else None
        cap = t["captain_id"] if t else None
        if not cap:
            continue
        try:
            await bot_instance.send_message(cap, text, reply_markup=reply_markup)
        except Exception as e:
            log.warning("Не удалось уведомить капитана %s: %s", cap, e)




def disqualify_team_in_bracket(team_id: int, skip_match_id: Optional[int] = None):
    matches = db_get_matches()
    for m in matches:
        if skip_match_id and m["id"] == skip_match_id:
            continue
        if m["team1_id"] != team_id and m["team2_id"] != team_id:
            continue

        new_t1 = m["team1_id"]
        new_t2 = m["team2_id"]
        if m["team1_id"] == team_id:
            new_t1 = None
        if m["team2_id"] == team_id:
            new_t2 = None

        updates = {"team1_id": new_t1, "team2_id": new_t2}

        if new_t1 and not new_t2:
            updates["winner_id"] = new_t1
            updates["status"] = "done"
        elif new_t2 and not new_t1:
            updates["winner_id"] = new_t2
            updates["status"] = "done"
        elif not new_t1 and not new_t2:
            updates["winner_id"] = None
            updates["status"] = "pending"

        db_update_match(m["id"], **updates)

async def post_match_result_summary(match_row):
    global REPORT_CHAT_ID
    if not REPORT_CHAT_ID:
        return
    score = "1:0" if match_row["winner_id"] == match_row["team1_id"] else "0:1"
    text = (
        f"🏆 <b>Итог матча</b>\n\n"
        f"{html.escape(team_name(match_row['team1_id']))} [{score}] "
        f"{html.escape(team_name(match_row['team2_id']))}\n"
        f"Формат: bo3\n"
        f"Победитель: <b>{html.escape(team_name(match_row['winner_id']))}</b>"
    )
    try:
        await bot_instance.send_message(REPORT_CHAT_ID, text)
    except TelegramMigrateToChat as e:
        REPORT_CHAT_ID = e.migrate_to_chat_id
        log.warning("Чат отчётов мигрирован, обновляю REPORT_CHAT_ID на %s", REPORT_CHAT_ID)
        try:
            await bot_instance.send_message(REPORT_CHAT_ID, text)
        except Exception as ex:
            log.warning("Не удалось отправить итог в REPORT_CHAT_ID после миграции: %s", ex)
    except Exception as e:
        log.warning("Не удалось отправить итог в REPORT_CHAT_ID: %s", e)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ФОРМАТИРОВАНИЕ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def fmt_bracket_full(matches: list) -> str:
    if not matches:
        return "Сетка ещё не составлена."
    bsize = matches[0]["bsize"]
    total = bsize.bit_length()
    by_r: dict[int, list] = {}
    for m in matches:
        by_r.setdefault(m["round"], []).append(m)

    lines = [
        f"{LINE}\n"
        f"⚔️  <b>ARMAGEDON CHAMPIONSHIP</b>\n"
        f"<b>Турнирная сетка  •  {bsize} слотов</b>\n"
        f"{LINE}"
    ]
    for rnd in sorted(by_r):
        lines.append(f"\n<b>{rname(rnd, total)}</b>")
        for m in by_r[rnd]:
            n1 = html.escape(team_name(m["team1_id"]))
            n2 = html.escape(team_name(m["team2_id"]))
            if m["team1_id"] is None and m["team2_id"] is None:
                lines.append(f"  {m['match_num']:>2}.  <i>ожидание...</i>")
                continue
            date_str = f"  📅 {m['match_date']}" if m["match_date"] else ""
            time_str = f" в {m['match_time']}" if m["match_time"] else ""
            w = m["winner_id"]
            s1 = " ✅" if w and w == m["team1_id"] else ""
            s2 = " ✅" if w and w == m["team2_id"] else ""
            lines.append(f"  {m['match_num']:>2}.  {n1}{s1}  vs  {n2}{s2}{date_str}{time_str}")
    return "\n".join(lines)


def fmt_team_schedule(team_id: int, matches: list) -> str:
    """Расписание конкретной команды."""
    t = db_get_team(team_id)
    if not t:
        return "Команда не найдена."
    bsize = matches[0]["bsize"] if matches else 2
    total = bsize.bit_length()

    my_matches = [m for m in matches
                  if m["team1_id"] == team_id or m["team2_id"] == team_id]

    if not my_matches:
        return f"Для команды <b>{html.escape(t['name'])}</b> матчей пока нет."

    lines = [
        f"{LINE}\n"
        f"📋  <b>Расписание: {html.escape(t['name'])}</b>\n"
        f"{LINE}"
    ]
    for m in my_matches:
        opp_id = m["team2_id"] if m["team1_id"] == team_id else m["team1_id"]
        opp    = html.escape(team_name(opp_id))
        rn     = rname(m["round"], total)
        date_s = m["match_date"] or "дата не назначена"
        time_s = m["match_time"] or ""
        w      = m["winner_id"]

        if w == team_id:
            result = "  ✅ Победа"
        elif w and w != team_id:
            result = "  ❌ Поражение"
        else:
            result = ""

        lines.append(
            f"\n<b>{rn}</b>\n"
            f"  Соперник: <b>{opp}</b>\n"
            f"  Дата: {date_s}{' в ' + time_s if time_s else ''}\n"
            f"  Статус: {fmt_status(m['status'])}{result}"
        )
    return "\n".join(lines)


def fmt_status(s: str) -> str:
    return {
        "pending":         "ожидание",
        "notified":        "уведомлены",
        "lobby_pending":   "⏳ ожидание лобби",
        "lobby_confirmed": "✅ лобби создано",
        "playing":         "🎮 идёт игра",
        "result_pending":  "⏳ ожидание итогов",
        "done":            "✅ завершён",
    }.get(s, s)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CALLBACK DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class Nav(CallbackData, prefix="n"):
    to: str


class MatchAction(CallbackData, prefix="ma"):
    action:   str
    match_id: int


class WinnerCB(CallbackData, prefix="win"):
    match_id: int
    team_id:  int


class ConfirmCB(CallbackData, prefix="cnf"):
    scr_id:   int
    approved: int   # 1 = да, 0 = нет

class ComplaintCB(CallbackData, prefix="cmp"):
    match_id: int
    team_id:  int


class ExcludeTeamCB(CallbackData, prefix="excl"):
    scr_id: int
    team_id: int


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FSM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class AuthState(StatesGroup):
    team_name = State()
    password  = State()


class AdminAddTeam(StatesGroup):
    name     = State()
    password = State()


class AdminSetDate(StatesGroup):
    match_id = State()
    date     = State()
    time     = State()


class ScreenshotWait(StatesGroup):
    lobby  = State()
    result = State()


class AdminBulkSchedule(StatesGroup):
    date = State()
    time = State()
    step = State()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  КЛАВИАТУРЫ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_main(user_id: int, is_captain: bool = False):
    b = InlineKeyboardBuilder()
    if is_captain:
        b.button(text="📋 Моё расписание",   callback_data=Nav(to="my_schedule"))
        b.button(text="🏆 Общая сетка",      callback_data=Nav(to="bracket"))
    else:
        b.button(text="🔑 Войти как капитан", callback_data=Nav(to="auth"))
        b.button(text="🏆 Общая сетка",      callback_data=Nav(to="bracket"))
    if user_id in ADMIN_IDS:
        b.button(text="⚙️ Панель админа",    callback_data=Nav(to="admin"))
    b.adjust(2, 1)
    return b.as_markup()


def kb_admin():
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить команду",    callback_data=Nav(to="add_team"))
    b.button(text="📋 Список команд",       callback_data=Nav(to="list_teams"))
    b.button(text="🎲 Сгенерировать сетку", callback_data=Nav(to="gen_bracket"))
    b.button(text="📅 Назначить дату матча",callback_data=Nav(to="set_date"))
    b.button(text="⚡ Быстрое расписание",callback_data=Nav(to="bulk_schedule"))
    b.button(text="📢 Уведомить команды",   callback_data=Nav(to="notify_matches"))
    b.button(text="🗑 Сбросить всё",        callback_data=Nav(to="reset_all"))
    b.button(text="◀️ Главное меню",        callback_data=Nav(to="home"))
    b.adjust(1)
    return b.as_markup()


def kb_back(to: str = "home"):
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Назад", callback_data=Nav(to=to))
    return b.as_markup()


def kb_home():
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Главное меню", callback_data=Nav(to="home"))
    return b.as_markup()


def kb_match_actions(match_id: int, team_id: int = 0):
    b = InlineKeyboardBuilder()
    b.button(text="🎮 Игра началась",  callback_data=MatchAction(action="start",  match_id=match_id))
    b.button(text="🏁 Игра завершена", callback_data=MatchAction(action="finish", match_id=match_id))
    b.button(text="🚨 Вызвать администратора",
             callback_data=ComplaintCB(match_id=match_id, team_id=team_id))
    b.adjust(2, 1)
    return b.as_markup()


def kb_winner(match_id: int, t1_id: int, t2_id: int):
    b = InlineKeyboardBuilder()
    b.button(text=f"🏆 {team_name(t1_id)}",
             callback_data=WinnerCB(match_id=match_id, team_id=t1_id))
    b.button(text=f"🏆 {team_name(t2_id)}",
             callback_data=WinnerCB(match_id=match_id, team_id=t2_id))
    b.adjust(2)
    return b.as_markup()


def kb_confirm(scr_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data=ConfirmCB(scr_id=scr_id, approved=1))
    b.button(text="❌ Отклонить",   callback_data=ConfirmCB(scr_id=scr_id, approved=0))
    b.adjust(2)
    return b.as_markup()


def kb_confirm_result(scr_id: int, t1_id: int, t2_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data=ConfirmCB(scr_id=scr_id, approved=1))
    b.button(text="❌ Отклонить", callback_data=ConfirmCB(scr_id=scr_id, approved=0))
    b.button(text=f"⛔ Исключить {team_name(t1_id)}",
             callback_data=ExcludeTeamCB(scr_id=scr_id, team_id=t1_id))
    b.button(text=f"⛔ Исключить {team_name(t2_id)}",
             callback_data=ExcludeTeamCB(scr_id=scr_id, team_id=t2_id))
    b.adjust(2, 1, 1)
    return b.as_markup()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ТЕКСТЫ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAIN_TEXT = (
    f"{LINE}\n"
    f"⚔️  <b>ARMAGEDON CHAMPIONSHIP</b>\n"
    f"{LINE}\n\n"
    f"Бот для управления матчами турнира.\n\n"
    f"Если ты капитан — войди в систему.\n"
    f"Если хочешь следить за сеткой — кнопка ниже."
)


def txt_ok(body: str) -> str:
    return f"{LINE}\n✅  <b>Готово</b>\n{LINE}\n\n{body}"


def txt_err(body: str) -> str:
    return f"{LINE}\n⚠️  <b>Внимание</b>\n{LINE}\n\n{body}"


def txt_section(title: str, body: str) -> str:
    return f"{LINE}\n<b>{title}</b>\n{LINE}\n\n{body}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ROUTER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
router = Router()
bot_instance: Bot = None


async def ack(cb: CallbackQuery):
    await cb.answer()


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ── /start ────────────────────────────────
@router.message(CommandStart())
async def on_start(msg: Message, state: FSMContext):
    await state.clear()
    uid       = msg.from_user.id
    cap_team  = db_get_captain_team(uid)
    await msg.answer(MAIN_TEXT,
                     reply_markup=kb_main(uid, is_captain=bool(cap_team)))


# ── Главное меню ──────────────────────────
@router.callback_query(Nav.filter(F.to == "home"))
async def cb_home(cb: CallbackQuery, state: FSMContext):
    await ack(cb)
    await state.clear()
    uid      = cb.from_user.id
    cap_team = db_get_captain_team(uid)
    await cb.message.answer(MAIN_TEXT,
                             reply_markup=kb_main(uid, is_captain=bool(cap_team)))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  АВТОРИЗАЦИЯ КАПИТАНА
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(Nav.filter(F.to == "auth"))
async def cb_auth(cb: CallbackQuery, state: FSMContext):
    await ack(cb)
    await state.set_state(AuthState.team_name)
    await cb.message.answer(
        txt_section("🔑 Авторизация капитана",
                    "Введи название своей команды:"),
        reply_markup=kb_back()
    )


@router.message(StateFilter(AuthState.team_name), F.text)
async def auth_team_name(msg: Message, state: FSMContext):
    t = db_get_team_by_name(msg.text.strip())
    if not t:
        await msg.answer(
            txt_err(f"Команда <b>{html.escape(msg.text)}</b> не найдена.\nПроверь название и попробуй снова."),
            reply_markup=kb_back()
        )
        return
    await state.update_data(team_id=t["id"], team_name=t["name"])
    await state.set_state(AuthState.password)
    await msg.answer(
        txt_section("🔑 Авторизация  —  шаг 2",
                    f"Команда: <b>{html.escape(t['name'])}</b>\n\nВведи пароль от администратора:"),
        reply_markup=kb_back("auth")
    )


@router.message(StateFilter(AuthState.password), F.text)
async def auth_password(msg: Message, state: FSMContext):
    data = await state.get_data()
    t    = db_get_team(data["team_id"])

    if msg.text.strip() != t["password"]:
        await msg.answer(
            txt_err("Неверный пароль. Попробуй ещё раз."),
            reply_markup=kb_back("auth")
        )
        return

    db_set_captain(t["id"], msg.from_user.id)
    await state.clear()
    await msg.answer(
        txt_ok(
            f"Ты авторизован как капитан команды <b>{html.escape(t['name'])}</b>!\n\n"
            f"Теперь тебе будут приходить уведомления о матчах."
        ),
        reply_markup=kb_main(msg.from_user.id, is_captain=True)
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ПРОСМОТР СЕТКИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(Nav.filter(F.to == "bracket"))
async def cb_bracket(cb: CallbackQuery):
    await ack(cb)
    ms = db_get_matches()
    if not ms:
        await cb.message.answer(
            txt_section("🏆 Турнирная сетка",
                        "Сетка ещё не составлена.\nОжидай объявления от организатора."),
            reply_markup=kb_home()
        )
        return
    await cb.message.answer(fmt_bracket_full(ms), reply_markup=kb_home())


@router.callback_query(Nav.filter(F.to == "my_schedule"))
async def cb_my_schedule(cb: CallbackQuery):
    await ack(cb)
    uid  = cb.from_user.id
    team = db_get_captain_team(uid)
    if not team:
        await cb.message.answer(
            txt_err("Ты не авторизован как капитан.\nНажми «Войти как капитан»."),
            reply_markup=kb_home()
        )
        return
    ms = db_get_matches()
    await cb.message.answer(
        fmt_team_schedule(team["id"], ms),
        reply_markup=kb_home()
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ПАНЕЛЬ АДМИНА
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(Nav.filter(F.to == "admin"))
async def cb_admin(cb: CallbackQuery):
    await ack(cb)
    if not is_admin(cb.from_user.id):
        await cb.message.answer(txt_err("Нет доступа."), reply_markup=kb_home())
        return
    teams = db_get_all_teams()
    ms    = db_get_matches()
    await cb.message.answer(
        txt_section("⚙️ Панель администратора",
                    f"Команд зарегистрировано:  <b>{len(teams)}</b>\n"
                    f"Матчей в сетке:           <b>{len(ms)}</b>"),
        reply_markup=kb_admin()
    )


# ── Добавить команду ─────────────────────
@router.callback_query(Nav.filter(F.to == "add_team"))
async def cb_add_team(cb: CallbackQuery, state: FSMContext):
    await ack(cb)
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(AdminAddTeam.name)
    await cb.message.answer(
        txt_section("➕ Добавить команду", "Введи название команды:"),
        reply_markup=kb_back("admin")
    )


@router.message(StateFilter(AdminAddTeam.name), F.text)
async def admin_team_name(msg: Message, state: FSMContext):
    await state.update_data(team_name=msg.text.strip())
    await state.set_state(AdminAddTeam.password)
    await msg.answer(
        txt_section("➕ Добавить команду  —  шаг 2",
                    f"Команда: <b>{html.escape(msg.text.strip())}</b>\n\n"
                    f"Теперь придумай пароль для капитана этой команды:"),
        reply_markup=kb_back("admin")
    )


@router.message(StateFilter(AdminAddTeam.password), F.text)
async def admin_team_password(msg: Message, state: FSMContext):
    data = await state.get_data()
    ok   = db_add_team(data["team_name"], msg.text.strip())
    await state.clear()
    if ok:
        await msg.answer(
            txt_ok(
                f"Команда добавлена!\n\n"
                f"Название: <b>{html.escape(data['team_name'])}</b>\n"
                f"Пароль:   <code>{html.escape(msg.text.strip())}</code>\n\n"
                f"Передай пароль капитану лично."
            ),
            reply_markup=kb_admin()
        )
    else:
        await msg.answer(
            txt_err(f"Команда с названием <b>{html.escape(data['team_name'])}</b> уже существует."),
            reply_markup=kb_admin()
        )


# ── Список команд ────────────────────────
@router.callback_query(Nav.filter(F.to == "list_teams"))
async def cb_list_teams(cb: CallbackQuery):
    await ack(cb)
    if not is_admin(cb.from_user.id):
        return
    teams = db_get_all_teams()
    if not teams:
        await cb.message.answer(
            txt_section("📋 Команды", "Команды ещё не добавлены."),
            reply_markup=kb_admin()
        )
        return
    lines = []
    for t in teams:
        cap = f"👤 капитан авторизован" if t["captain_id"] else "⏳ капитан не вошёл"
        lines.append(f"  <b>{html.escape(t['name'])}</b>  —  {cap}\n"
                     f"  🔑 пароль: <code>{html.escape(t['password'])}</code>")
    await cb.message.answer(
        txt_section("📋 Зарегистрированные команды", "\n\n".join(lines)),
        reply_markup=kb_admin()
    )


# ── Генерация сетки ──────────────────────
@router.callback_query(Nav.filter(F.to == "gen_bracket"))
async def cb_gen_bracket(cb: CallbackQuery):
    await ack(cb)
    if not is_admin(cb.from_user.id):
        return
    teams = db_get_all_teams()
    if len(teams) < 2:
        await cb.message.answer(
            txt_err("Нужно минимум 2 команды."),
            reply_markup=kb_admin()
        )
        return
    bsize, pairs = make_bracket(teams)
    db_save_bracket(bsize, pairs)
    byes = sum(1 for a, b in pairs if a is None or b is None)
    await cb.message.answer(
        txt_ok(
            f"Сетка сгенерирована!\n\n"
            f"Команд:       <b>{len(teams)}</b>\n"
            f"Размер сетки: <b>{bsize}</b>\n"
            f"BYE слотов:   <b>{byes}</b>"
        ),
        reply_markup=kb_admin()
    )


# ── Назначить дату матча ─────────────────
@router.callback_query(Nav.filter(F.to == "set_date"))
async def cb_set_date_start(cb: CallbackQuery, state: FSMContext):
    await ack(cb)
    if not is_admin(cb.from_user.id):
        return
    ms = db_get_matches()
    pending = [m for m in ms if m["team1_id"] and m["team2_id"]
               and not m["match_date"]]
    if not pending:
        await cb.message.answer(
            txt_err("Нет матчей без назначенной даты."),
            reply_markup=kb_admin()
        )
        return

    lines = []
    for m in pending[:10]:
        lines.append(f"  ID <code>{m['id']}</code>  —  "
                     f"{html.escape(team_name(m['team1_id']))} vs "
                     f"{html.escape(team_name(m['team2_id']))}")

    await state.set_state(AdminSetDate.match_id)
    await cb.message.answer(
        txt_section("📅 Назначить дату матча",
                    "Матчи без даты:\n\n" + "\n".join(lines) +
                    "\n\nВведи ID матча:"),
        reply_markup=kb_back("admin")
    )


@router.message(StateFilter(AdminSetDate.match_id), F.text)
async def set_date_match_id(msg: Message, state: FSMContext):
    try:
        mid = int(msg.text.strip())
    except ValueError:
        await msg.answer(txt_err("Введи число — ID матча."))
        return
    m = db_get_match(mid)
    if not m:
        await msg.answer(txt_err("Матч не найден."))
        return
    await state.update_data(match_id=mid)
    await state.set_state(AdminSetDate.date)
    await msg.answer(
        txt_section("📅 Дата матча",
                    f"{html.escape(team_name(m['team1_id']))} vs "
                    f"{html.escape(team_name(m['team2_id']))}\n\n"
                    f"Введи дату в формате ДД.ММ.ГГГГ:"),
        reply_markup=kb_back("admin")
    )


@router.message(StateFilter(AdminSetDate.date), F.text)
async def set_date_date(msg: Message, state: FSMContext):
    await state.update_data(date=msg.text.strip())
    await state.set_state(AdminSetDate.time)
    await msg.answer(
        txt_section("📅 Время матча",
                    f"Дата: <b>{msg.text.strip()}</b>\n\nВведи время в формате ЧЧ:ММ:"),
        reply_markup=kb_back("admin")
    )


@router.message(StateFilter(AdminSetDate.time), F.text)
async def set_date_time(msg: Message, state: FSMContext):
    data = await state.get_data()
    db_update_match(data["match_id"],
                    match_date=data["date"],
                    match_time=msg.text.strip())
    await state.clear()
    m = db_get_match(data["match_id"])
    await msg.answer(
        txt_ok(
            f"Дата матча назначена!\n\n"
            f"{html.escape(team_name(m['team1_id']))} vs "
            f"{html.escape(team_name(m['team2_id']))}\n"
            f"📅 {data['date']} в {msg.text.strip()}"
        ),
        reply_markup=kb_admin()
    )




@router.callback_query(Nav.filter(F.to == "bulk_schedule"))
async def cb_bulk_schedule_start(cb: CallbackQuery, state: FSMContext):
    await ack(cb)
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(AdminBulkSchedule.date)
    await cb.message.answer(
        txt_section("⚡ Быстрое расписание",
                    "Введи дату для серии матчей в формате ДД.ММ.ГГГГ:"),
        reply_markup=kb_back("admin")
    )


@router.message(StateFilter(AdminBulkSchedule.date), F.text)
async def bulk_schedule_date(msg: Message, state: FSMContext):
    await state.update_data(date=msg.text.strip())
    await state.set_state(AdminBulkSchedule.time)
    await msg.answer(txt_section("⚡ Быстрое расписание", "Введи время первого матча (ЧЧ:ММ):"), reply_markup=kb_back("admin"))


@router.message(StateFilter(AdminBulkSchedule.time), F.text)
async def bulk_schedule_time(msg: Message, state: FSMContext):
    await state.update_data(time=msg.text.strip())
    await state.set_state(AdminBulkSchedule.step)
    await msg.answer(txt_section("⚡ Быстрое расписание", "Шаг между матчами в минутах (например 30).\nЕсли хочешь всем матчам одинаковое время — введи <b>0</b>."), reply_markup=kb_back("admin"))


@router.message(StateFilter(AdminBulkSchedule.step), F.text)
async def bulk_schedule_step(msg: Message, state: FSMContext):
    data = await state.get_data()
    try:
        step = int(msg.text.strip())
    except ValueError:
        await msg.answer(txt_err("Нужно число минут."))
        return

    ms_all = [m for m in db_get_matches() if m["team1_id"] and m["team2_id"] and not m["match_date"]]
    if not ms_all:
        await state.clear()
        await msg.answer(txt_err("Нет матчей без даты."), reply_markup=kb_admin())
        return

    target_round = min(m["round"] for m in ms_all)
    ms = [m for m in ms_all if m["round"] == target_round]

    base = datetime.strptime(f"{data['date']} {data['time']}", "%d.%m.%Y %H:%M")
    for i, m in enumerate(ms):
        dt = base + timedelta(minutes=step * i)
        db_update_match(m["id"], match_date=dt.strftime("%d.%m.%Y"), match_time=dt.strftime("%H:%M"))

    await state.clear()
    if step == 0:
        mode = "Все матчи выбранного раунда поставлены на одно время"
    else:
        mode = f"Матчи раунда расставлены с шагом {step} мин"

    await msg.answer(
        txt_ok(
            f"Быстрое расписание применено.\n"
            f"Раунд: <b>{target_round}</b>\n"
            f"Матчей: <b>{len(ms)}</b>\n"
            f"Режим: {mode}"
        ),
        reply_markup=kb_admin()
    )

# ── Уведомить команды о матчах ───────────
@router.callback_query(Nav.filter(F.to == "notify_matches"))
async def cb_notify_matches(cb: CallbackQuery):
    await ack(cb)
    if not is_admin(cb.from_user.id):
        return

    ms = db_get_matches()
    to_notify = [m for m in ms
                 if m["team1_id"] and m["team2_id"]
                 and m["match_date"]
                 and m["status"] == "pending"]

    if not to_notify:
        await cb.message.answer(
            txt_err("Нет матчей с назначенной датой для уведомления."),
            reply_markup=kb_admin()
        )
        return

    sent = 0
    for m in to_notify:
        db_update_match(m["id"], status="notified")
        for tid in [m["team1_id"], m["team2_id"]]:
            if tid is None:
                continue
            t     = db_get_team(tid)
            cap   = t["captain_id"] if t else None
            if not cap:
                continue
            opp_id = m["team2_id"] if tid == m["team1_id"] else m["team1_id"]
            try:
                await bot_instance.send_message(
                    cap,
                    f"{LINE}\n"
                    f"⚔️  <b>ARMAGEDON CHAMPIONSHIP</b>\n"
                    f"{LINE}\n\n"
                    f"📅 <b>Твой матч назначен!</b>\n\n"
                    f"Соперник: <b>{html.escape(team_name(opp_id))}</b>\n"
                    f"Дата: <b>{m['match_date']} в {m['match_time'] or '—'}</b>\n\n"
                    f"В день матча бот пришлёт напоминание и выберет кто создаёт лобби."
                )
                sent += 1
            except Exception as e:
                log.warning(f"Не удалось уведомить капитана {cap}: {e}")

    await cb.message.answer(
        txt_ok(f"Уведомления отправлены.\nОхвачено капитанов: <b>{sent}</b>"),
        reply_markup=kb_admin()
    )


# ── Сброс ────────────────────────────────
@router.callback_query(Nav.filter(F.to == "reset_all"))
async def cb_reset_all(cb: CallbackQuery):
    await ack(cb)
    if not is_admin(cb.from_user.id):
        return
    with _lk:
        _con.executescript("""
            DELETE FROM matches;
            DELETE FROM screenshots;
            DELETE FROM captain_sessions;
            UPDATE teams SET captain_id = NULL;
        """)
        _con.commit()
    await cb.message.answer(
        txt_ok("Сетка, сессии и скрины сброшены.\nКоманды сохранены."),
        reply_markup=kb_admin()
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  МАТЧЕВЫЙ ФЛОУ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_match_day_notification(match_id: int):
    """Отправляет уведомление о дне игры обеим командам и выбирает создателя лобби."""
    m = db_get_match(match_id)
    if not m or not m["team1_id"] or not m["team2_id"]:
        return

    # Рандомно выбираем кто создаёт лобби
    lobby_tid = random.choice([m["team1_id"], m["team2_id"]])
    db_update_match(match_id, status="lobby_pending", lobby_team_id=lobby_tid)

    opp = {m["team1_id"]: m["team2_id"], m["team2_id"]: m["team1_id"]}

    for tid in [m["team1_id"], m["team2_id"]]:
        t   = db_get_team(tid)
        cap = t["captain_id"] if t else None
        if not cap:
            continue
        opp_name = html.escape(team_name(opp[tid]))

        if tid == lobby_tid:
            action_text = (
                f"🎯 <b>Твоя команда создаёт лобби!</b>\n\n"
                f"Создай лобби в Dota 2, пригласи соперника и отправь скрин сюда."
            )
        else:
            action_text = (
                f"⏳ Соперник создаёт лобби. Ожидай приглашения."
            )

        try:
            await bot_instance.send_message(
                cap,
                f"{LINE}\n"
                f"⚔️  <b>СЕГОДНЯ ТВОЙ МАТЧ!</b>\n"
                f"{LINE}\n\n"
                f"Соперник: <b>{opp_name}</b>\n"
                f"Время: <b>{m['match_time'] or 'по договорённости'}</b>\n\n"
                f"{action_text}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="📸 Отправить скрин лобби",
                        callback_data=MatchAction(action="send_lobby_scr",
                                                  match_id=match_id).pack()
                    )
                ]]) if tid == lobby_tid else None
            )
        except Exception as e:
            log.warning(f"Не удалось отправить матч-дей {cap}: {e}")


@router.callback_query(MatchAction.filter(F.action == "send_lobby_scr"))
async def cb_send_lobby_scr(cb: CallbackQuery,
                             callback_data: MatchAction,
                             state: FSMContext):
    await ack(cb)
    await state.update_data(match_id=callback_data.match_id,
                             scr_type="lobby")
    _pending_lobby_screenshots[cb.from_user.id] = callback_data.match_id
    await state.set_state(ScreenshotWait.lobby)
    await cb.message.answer(
        txt_section("📸 Скрин лобби",
                    "Сделай скриншот созданного лобби и отправь его сюда.\n"
                    "Скрин будет передан администратору для подтверждения.")
    )


@router.message(StateFilter(ScreenshotWait.lobby), F.photo)
async def receive_lobby_screenshot(msg: Message, state: FSMContext):
    data     = await state.get_data()
    match_id = data["match_id"]
    team     = db_get_captain_team(msg.from_user.id)
    if not team:
        await msg.answer(txt_err("Ты не авторизован как капитан."))
        return

    file_id = msg.photo[-1].file_id
    scr_id  = db_save_screenshot(match_id, "lobby", file_id,
                                  msg.from_user.id, team["id"])
    await state.clear()

    # Сохраняем возможность отправить скрин повторно, если админ отклонит
    _pending_lobby_screenshots[msg.from_user.id] = match_id

    # Шлём админам
    m = db_get_match(match_id)
    caption = (
        f"📸 <b>Скрин лобби</b>\n\n"
        f"Матч: <b>{html.escape(team_name(m['team1_id']))} vs "
        f"{html.escape(team_name(m['team2_id']))}</b>\n"
        f"Команда: <b>{html.escape(team['name'])}</b>\n"
        f"ID скрина: <code>{scr_id}</code>"
    )
    for aid in ADMIN_IDS:
        try:
            await bot_instance.send_photo(
                aid,
                photo=file_id,
                caption=caption,
                reply_markup=kb_confirm_result(scr_id, m["team1_id"], m["team2_id"])
            )
        except Exception as e:
            log.warning(f"Не удалось отправить скрин админу {aid}: {e}")

    await msg.answer(
        txt_ok("Скрин отправлен администратору.\nОжидай подтверждения.")
    )


@router.callback_query(ConfirmCB.filter())
async def cb_confirm(cb: CallbackQuery, callback_data: ConfirmCB):
    await ack(cb)
    if not is_admin(cb.from_user.id):
        return

    scr = db_get_screenshot(callback_data.scr_id)
    if not scr:
        await cb.answer("Скрин не найден.", show_alert=True)
        return

    m       = db_get_match(scr["match_id"])
    approved = callback_data.approved == 1

    if approved:
        db_confirm_screenshot(callback_data.scr_id)

        if scr["type"] == "lobby":
            db_update_match(scr["match_id"], status="lobby_confirmed")
            # Уведомляем обе команды
            for tid in [m["team1_id"], m["team2_id"]]:
                t   = db_get_team(tid)
                cap = t["captain_id"] if t else None
                if not cap:
                    continue
                try:
                    await bot_instance.send_message(
                        cap,
                        f"{LINE}\n✅  <b>Лобби подтверждено!</b>\n{LINE}\n\n"
                        f"Администратор подтвердил создание лобби.\n"
                        f"Как только игра начнётся — нажми кнопку ниже.",
                        reply_markup=kb_match_actions(scr["match_id"], tid)
                    )
                except Exception as e:
                    log.warning(e)

        elif scr["type"] == "result":
            db_update_match(scr["match_id"], status="done")
            m2 = db_get_match(scr["match_id"])
            winner = html.escape(team_name(m2["winner_id"]))
            await notify_both_teams(
                m2,
                txt_ok(
                    f"Администратор подтвердил результат матча.\n"
                    f"Победитель: <b>{winner}</b>.\n"
                    f"Спасибо за игру!"
                )
            )
            await post_match_result_summary(m2)

        await cb.message.edit_caption(
            caption=(cb.message.caption or "") + "\n\n✅ <b>Подтверждено</b>"
        )

    else:
        await cb.message.edit_caption(
            caption=(cb.message.caption or "") + "\n\n❌ <b>Отклонено</b>"
        )
        # Уведомляем капитана
        t   = db_get_team(scr["team_id"])
        cap = t["captain_id"] if t else None
        if cap:
            try:
                await bot_instance.send_message(
                    cap,
                    txt_err(f"Скрин отклонён администратором.\nПопробуй отправить снова.")
                )
            except Exception:
                pass


# ── Игра началась ────────────────────────
@router.callback_query(MatchAction.filter(F.action == "start"))
async def cb_game_start(cb: CallbackQuery, callback_data: MatchAction):
    await ack(cb)
    mid  = callback_data.match_id
    m    = db_get_match(mid)
    team = db_get_captain_team(cb.from_user.id)

    if not team or (team["id"] != m["team1_id"] and team["id"] != m["team2_id"]):
        await cb.answer("Ты не участник этого матча.", show_alert=True)
        return

    db_update_match(mid, status="playing")

    # Уведомляем обоих капитанов
    for tid in [m["team1_id"], m["team2_id"]]:
        t   = db_get_team(tid)
        cap = t["captain_id"] if t else None
        if not cap:
            continue
        try:
            await bot_instance.send_message(
                cap,
                f"{LINE}\n🎮  <b>ИГРА НАЧАЛАСЬ!</b>\n{LINE}\n\n"
                f"{html.escape(team_name(m['team1_id']))} vs "
                f"{html.escape(team_name(m['team2_id']))}\n\n"
                f"Когда игра завершится — нажми кнопку ниже.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🏁 Игра завершена",
                        callback_data=MatchAction(
                            action="finish", match_id=mid).pack()
                    )
                ]])
            )
        except Exception as e:
            log.warning(e)

    await cb.message.edit_reply_markup(reply_markup=None)


# ── Игра завершена ───────────────────────
@router.callback_query(MatchAction.filter(F.action == "finish"))
async def cb_game_finish(cb: CallbackQuery, callback_data: MatchAction):
    await ack(cb)
    mid  = callback_data.match_id
    m    = db_get_match(mid)
    team = db_get_captain_team(cb.from_user.id)

    if not team or (team["id"] != m["team1_id"] and team["id"] != m["team2_id"]):
        await cb.answer("Ты не участник этого матча.", show_alert=True)
        return

    db_update_match(mid, status="result_pending")

    # Запрашиваем подтверждение исхода у соперника
    await cb.message.edit_reply_markup(reply_markup=None)
    opp_id = other_team_id(m, team["id"])
    opp = db_get_team(opp_id) if opp_id else None
    opp_cap = opp["captain_id"] if opp else None

    if opp_cap:
        await bot_instance.send_message(
            opp_cap,
            txt_section("🏁 Игра завершена",
                        f"Соперник отметил завершение матча.\n"
                        f"Подтверди исход: кто победил?"),
            reply_markup=kb_winner(mid, m["team1_id"], m["team2_id"])
        )
    await cb.message.answer(txt_ok("Запрос подтверждения отправлен сопернику."))


# ── Выбор победителя ─────────────────────
@router.callback_query(WinnerCB.filter())
async def cb_winner(cb: CallbackQuery, callback_data: WinnerCB):
    await ack(cb)
    mid     = callback_data.match_id
    win_tid = callback_data.team_id
    team    = db_get_captain_team(cb.from_user.id)
    m       = db_get_match(mid)

    if not team or (team["id"] != m["team1_id"] and team["id"] != m["team2_id"]):
        await cb.answer("Ты не участник этого матча.", show_alert=True)
        return

    db_update_match(mid, winner_id=win_tid)

    # Просим скрин результата
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        txt_section("📸 Подтверждение итогов",
                    f"Ты указал победителем: <b>{html.escape(team_name(win_tid))}</b>\n\n"
                    f"Отправь скриншот таблицы результатов для подтверждения администратором.")
    )

    await notify_both_teams(
        m,
        txt_section("🏁 Исход заявлен",
                    f"Заявленный победитель: <b>{html.escape(team_name(win_tid))}</b>.\n"
                    f"Ожидаем подтверждение администратора.")
    )

    # Сохраняем ожидание скрина через state
    # Используем глобальный FSM через отдельный хендлер
    # Отмечаем что ждём скрин от этого пользователя
    _pending_result_screenshots[cb.from_user.id] = {
        "match_id": mid,
        "team_id":  team["id"]
    }


# Временное хранилище ожидания скринов лобби
_pending_lobby_screenshots: dict = {}

# Временное хранилище ожидания скринов результата
_pending_result_screenshots: dict = {}


@router.message(F.photo)
async def receive_any_photo(msg: Message, state: FSMContext):
    uid = msg.from_user.id

    # Скрин результата
    if uid in _pending_result_screenshots:
        info     = _pending_result_screenshots.pop(uid)
        file_id  = msg.photo[-1].file_id
        scr_id   = db_save_screenshot(info["match_id"], "result",
                                       file_id, uid, info["team_id"])
        m        = db_get_match(info["match_id"])
        team     = db_get_team(info["team_id"])
        win_name = html.escape(team_name(m["winner_id"]))

        caption = (
            f"📸 <b>Скрин результата</b>\n\n"
            f"Матч: <b>{html.escape(team_name(m['team1_id']))} vs "
            f"{html.escape(team_name(m['team2_id']))}</b>\n"
            f"Победитель (заявлен): <b>{win_name}</b>\n"
            f"Команда: <b>{html.escape(team['name'])}</b>\n"
            f"ID скрина: <code>{scr_id}</code>"
        )
        for aid in ADMIN_IDS:
            try:
                await bot_instance.send_photo(
                    aid,
                    photo=file_id,
                    caption=caption,
                    reply_markup=kb_confirm_result(scr_id, m["team1_id"], m["team2_id"])
                )
            except Exception as e:
                log.warning(e)

        await msg.answer(txt_ok("Скрин результата отправлен администратору.\nОжидай подтверждения."))

        # Уведомляем всех о победителе после подтверждения (в confirm handler)
        db_update_match(info["match_id"], status="result_pending")
        return

    # Повторная отправка скрина лобби после отклонения
    if uid in _pending_lobby_screenshots:
        match_id = _pending_lobby_screenshots[uid]
        team = db_get_captain_team(uid)
        if not team:
            await msg.answer(txt_err("Ты не авторизован как капитан."))
            return

        file_id = msg.photo[-1].file_id
        scr_id = db_save_screenshot(match_id, "lobby", file_id, uid, team["id"])

        m = db_get_match(match_id)
        caption = (
            f"📸 <b>Скрин лобби (повтор)</b>\n\n"
            f"Матч: <b>{html.escape(team_name(m['team1_id']))} vs "
            f"{html.escape(team_name(m['team2_id']))}</b>\n"
            f"Команда: <b>{html.escape(team['name'])}</b>\n"
            f"ID скрина: <code>{scr_id}</code>"
        )
        for aid in ADMIN_IDS:
            try:
                await bot_instance.send_photo(
                    aid,
                    photo=file_id,
                    caption=caption,
                    reply_markup=kb_confirm(scr_id)
                )
            except Exception as e:
                log.warning(e)

        await msg.answer(txt_ok("Новый скрин лобби отправлен администратору.\nОжидай подтверждения."))
        return

    # Остальные фото игнорируем
    cur_state = await state.get_state()
    if not cur_state and msg.chat.type == "private":
        await msg.answer(
            "Чтобы отправить скрин, сначала нажми нужную кнопку в сообщении от бота.",
            reply_markup=kb_home()
        )


@router.callback_query(ExcludeTeamCB.filter())
async def cb_exclude_team(cb: CallbackQuery, callback_data: ExcludeTeamCB):
    await ack(cb)
    if not is_admin(cb.from_user.id):
        return

    scr = db_get_screenshot(callback_data.scr_id)
    if not scr:
        await cb.answer("Скрин не найден.", show_alert=True)
        return

    m = db_get_match(scr["match_id"])
    if not m:
        await cb.answer("Матч не найден.", show_alert=True)
        return

    excl_team_id = callback_data.team_id
    db_update_match(m["id"], status="done")
    disqualify_team_in_bracket(excl_team_id)

    # Победителем текущего матча делаем противоположную команду (если есть)
    winner_id = m["team2_id"] if excl_team_id == m["team1_id"] else m["team1_id"]
    if winner_id:
        db_update_match(m["id"], winner_id=winner_id, status="done")
        m = db_get_match(m["id"])

    excl_team = db_get_team(excl_team_id)
    excl_name = html.escape(excl_team["name"]) if excl_team else team_name(excl_team_id)

    await cb.message.edit_caption(
        caption=(cb.message.caption or "") + f"\n\n⛔ <b>Исключена команда:</b> {excl_name}"
    )

    if winner_id:
        await notify_both_teams(
            m,
            txt_section(
                "⛔ Решение администратора",
                f"Команда <b>{excl_name}</b> исключена из турнира.\n"
                f"Победителем матча назначена команда <b>{html.escape(team_name(winner_id))}</b>."
            )
        )
        await post_match_result_summary(m)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЖАЛОБА — ВЫЗОВ АДМИНИСТРАТОРА
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(ComplaintCB.filter())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ФОЛБЭК
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.callback_query(ComplaintCB.filter())
async def cb_complaint(cb: CallbackQuery, callback_data: ComplaintCB):
    await ack(cb)
    uid  = cb.from_user.id
    team = db_get_captain_team(uid)
    m    = db_get_match(callback_data.match_id)

    if not team or not m:
        await cb.answer("Ошибка - матч не найден.", show_alert=True)
        return

    opp_id   = m["team2_id"] if team["id"] == m["team1_id"] else m["team1_id"]
    opp_name = html.escape(team_name(opp_id))
    username = cb.from_user.username or "нет username"

    parts = [
        LINE,
        "🚨  <b>ЖАЛОБА В МАТЧЕ!</b>",
        LINE,
        "",
        "Команда: <b>" + html.escape(team["name"]) + "</b>",
        "Матч: <b>" + html.escape(team_name(m["team1_id"])) + " vs " + opp_name + "</b>",
        "Капитан: @" + username + " (<code>" + str(uid) + "</code>)",
        "",
        "⚠️ Капитан просит вмешательства!",
        "Свяжись с ним как можно скорее."
    ]
    admin_text = "\n".join(parts)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💬 Написать капитану",
                             url="tg://user?id=" + str(uid))
    ]])

    for aid in ADMIN_IDS:
        try:
            await bot_instance.send_message(aid, admin_text, reply_markup=kb)
        except Exception as e:
            log.warning("Жалоба не доставлена %s: %s", aid, e)

    cap_parts = [
        LINE,
        "🚨  <b>Администратор вызван</b>",
        LINE,
        "",
        "Твоя жалоба отправлена.",
        "Администратор свяжется с тобой в ближайшее время.",
        "",
        "<i>Не покидай матч пока не получишь ответ.</i>"
    ]
    await cb.message.answer("\n".join(cap_parts))
    log.info("Жалоба от %s (%s) в матче %s", uid, team["name"], m["id"])


@router.message()
async def fallback(msg: Message, state: FSMContext):
    # В группах/каналах бот не ведёт диалог игроков
    if msg.chat.type != "private":
        return

    if await state.get_state() is None:
        uid      = msg.from_user.id
        cap_team = db_get_captain_team(uid)
        await msg.answer(
            "Используй кнопки меню 👇",
            reply_markup=kb_main(uid, is_captain=bool(cap_team))
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  АВТОПЛАНИРОВЩИК УВЕДОМЛЕНИЙ (МСК)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def scheduler_loop():
    """Каждую минуту проверяет матчи и шлёт уведомление за 20 мин до начала."""
    log.info("⏰ Планировщик уведомлений запущен (турнирный TZ, за 20 мин)")
    while True:
        try:
            now_tz = datetime.now(TOURNAMENT_TZ)
            ms = db_get_matches()
            for m in ms:
                if not m["match_date"] or not m["match_time"]:
                    continue
                if m["status"] not in ("pending", "notified"):
                    continue
                if m["id"] in _notified_matches:
                    continue
                if not m["team1_id"] or not m["team2_id"]:
                    continue
                try:
                    match_dt = datetime.strptime(
                        f"{m['match_date']} {m['match_time']}",
                        "%d.%m.%Y %H:%M"
                    ).replace(tzinfo=TOURNAMENT_TZ)
                except ValueError:
                    continue

                delta = (match_dt - now_tz).total_seconds() / 60
                # Уведомляем в окне от 20 до 19 минут до матча
                if 0 <= delta <= NOTIFY_BEFORE_MINUTES and m["id"] not in _notified_matches:
                    log.info(f"⏰ Авто-уведомление матча {m['id']} ({delta:.1f} мин до начала)")
                    _notified_matches.add(m["id"])
                    await send_match_day_notification(m["id"])
        except Exception as e:
            log.error(f"Ошибка планировщика: {e}")
        await asyncio.sleep(60)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ЗАПУСК
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def main():
    global bot_instance

    init_db()

    bot_instance = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    log.info("⚔️  ARMAGEDON CHAMPIONSHIP Match Bot запущен!")
    # Запускаем планировщик уведомлений фоном
    asyncio.create_task(scheduler_loop())
    await dp.start_polling(bot_instance,
                           allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())