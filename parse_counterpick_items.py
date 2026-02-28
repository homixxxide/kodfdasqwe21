"""Парсер/генератор предметов для контрпика.

В условиях ограничений сети формирует полный локальный датасет для известных героев.
"""

from __future__ import annotations

import json
from pathlib import Path

from hero_roles import get_all_known_heroes

OUT_FILE = Path("hero_counterpick_items.json")

SUPPORT_ITEMS = [
    ("ghost_scepter", "Ghost Scepter", "Неуязвимость к физ. урону", 9, 1500),
    ("force_staff", "Force Staff", "Сброс позиции и сейв", 8, 2200),
    ("glimmer_cape", "Glimmer Cape", "Инвиз для сейва", 7, 1950),
    ("lotus_orb", "Lotus Orb", "Диспел и отражение", 8, 3850),
    ("aeon_disk", "Aeon Disk", "Анти-бёрст", 9, 3000),
]

CORE_ITEMS = [
    ("black_king_bar", "Black King Bar", "Иммунитет к контролю", 9, 4050),
    ("monkey_king_bar", "Monkey King Bar", "True Strike против уклонения", 9, 5400),
    ("nullifier", "Nullifier", "Сбивает сейв-предметы", 8, 4725),
    ("silver_edge", "Silver Edge", "Break ключевых пассивок", 8, 5450),
    ("abyssal_blade", "Abyssal Blade", "Надежный контроль цели", 8, 6250),
]

SPECIAL_MAP = {
    "phantom_assassin": {
        "core_items": [
            ("monkey_king_bar", "Monkey King Bar", "True Strike против Blur", 10, 5400),
            ("silver_edge", "Silver Edge", "Break отключает Blur", 9, 5450),
            ("bloodthorn", "Bloodthorn", "True Strike + сайленс", 8, 6800),
        ],
        "support_items": [
            ("ghost_scepter", "Ghost Scepter", "Неуязвимость к физ. урону", 10, 1500),
            ("force_staff", "Force Staff", "Спастись от Blink Strike", 8, 2200),
            ("glimmer_cape", "Glimmer Cape", "Инвиз для себя/тиммейта", 7, 1950),
        ],
    },
    "anti_mage": {
        "core_items": [
            ("orchid", "Orchid Malevolence", "Сайленс запрещает Blink", 10, 3975),
            ("abyssal_blade", "Abyssal Blade", "БКБ-пробивающий стан", 9, 6250),
        ],
        "support_items": [
            ("rod_of_atos", "Rod of Atos", "Рут останавливает Blink", 9, 2750),
        ],
    },
}


def _to_entry(tup):
    item, name, reason, priority, price = tup
    return {
        "item": item,
        "name": name,
        "reason": reason,
        "priority": priority,
        "price": price,
    }


def build_dataset():
    data = {}
    heroes = get_all_known_heroes()
    for hero in heroes:
        if hero in SPECIAL_MAP:
            data[hero] = {
                "core_items": [_to_entry(x) for x in SPECIAL_MAP[hero]["core_items"]],
                "support_items": [_to_entry(x) for x in SPECIAL_MAP[hero]["support_items"]],
            }
            continue
        data[hero] = {
            "core_items": [_to_entry(x) for x in CORE_ITEMS[:3]],
            "support_items": [_to_entry(x) for x in SUPPORT_ITEMS[:3]],
        }
    return data


def main():
    data = build_dataset()
    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Готово! Собрано данных для {len(data)} героев")


if __name__ == "__main__":
    main()
