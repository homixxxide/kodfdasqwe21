"""
Hero Roles Database
Роли героев для фильтрации контрпиков
"""

HERO_ROLES = {
    "Hard Support": [
        "crystal_maiden", "shadow_shaman", "witch_doctor", "warlock", "dazzle",
        "oracle", "chen", "io", "undying", "abaddon", "winter_wyvern",
        "vengeful_spirit", "ogre_magi", "jakiro", "disruptor", "keeper_of_the_light",
        "shadow_demon", "bane", "lich", "ancient_apparition", "enchantress",
        "omniknight", "treant_protector", "dark_willow", "grimstroke", "marci",
        "snapfire", "hoodwink", "silencer", "ringmaster"
    ],
    "Support": [
        "lion", "rubick", "earth_spirit", "mirana", "nyx_assassin",
        "phoenix", "pugna", "skywrath_mage", "spirit_breaker", "tusk",
        "venomancer", "windranger", "clockwerk", "earthshaker", "tiny",
        "elder_titan", "enigma", "furion", "sand_king", "pudge",
        "bounty_hunter", "techies",
        "grimstroke", "dark_willow", "snapfire", "hoodwink", "ringmaster", "largo"
    ],
    "Offlaner": [
        "axe", "mars", "tidehunter", "centaur_warrunner", "bristleback",
        "underlord", "doom", "legion_commander", "slardar", "sand_king",
        "dark_seer", "batrider", "beastmaster", "brewmaster", "dragon_knight",
        "night_stalker", "primal_beast", "timbersaw", "pangolier", "magnus",
        "spirit_breaker", "clockwerk", "omniknight", "death_prophet",
        "razor", "viper", "enigma", "enchantress",
        "phoenix", "elder_titan", "earthshaker", "kez", "largo", "shredder"
    ],
    "Mider": [
        "shadow_fiend", "storm_spirit", "invoker", "queen_of_pain", "puck",
        "templar_assassin", "ember_spirit", "outworld_destroyer", "tinker",
        "leshrac", "lina", "zeus", "void_spirit", "kunkka", "death_prophet",
        "necrophos", "viper", "huskar", "broodmother", "arc_warden",
        "alchemist", "bloodseeker", "sniper", "windranger", "batrider",
        "pangolier", "dragon_knight", "keeper_of_the_light", "tiny",
        "meepo", "visage", "lone_druid", "kez", "largo"
    ],
    "Carry": [
        "anti_mage", "phantom_assassin", "juggernaut", "slark", "faceless_void",
        "spectre", "terrorblade", "morphling", "naga_siren", "medusa",
        "phantom_lancer", "luna", "gyrocopter", "lifestealer", "ursa",
        "troll_warlord", "wraith_king", "sven", "chaos_knight", "drow_ranger",
        "weaver", "riki", "bloodseeker", "clinkz", "monkey_king",
        "muerta", "void_spirit", "ember_spirit", "alchemist",
        "templar_assassin", "razor", "kez"
    ]
}


def get_role_for_hero(hero_internal_name):
    """Возвращает роль героя или None."""
    if not hero_internal_name:
        return None
    hero_internal_name = hero_internal_name.lower()
    for role, heroes in HERO_ROLES.items():
        if hero_internal_name in heroes:
            return role
    return None


def get_heroes_by_role(role):
    """Возвращает список героев определенной роли."""
    return HERO_ROLES.get(role, [])


def get_all_known_heroes():
    all_heroes = []
    for heroes in HERO_ROLES.values():
        all_heroes.extend(heroes)
    return sorted(set(all_heroes))
