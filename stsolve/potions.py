"""Potion effects.

Numbers are taken from the game's own potion switch as reimplemented in
sts_lightspeed (``BattleContext::drinkPotion``) rather than from memory. Each
value is ``(base, with Sacred Bark)``.

Only potions whose effect a single-turn model can actually score are listed
here. Everything else is named in UNSCOREABLE so the CLI can say "I know this
potion and I am deliberately not modelling it" instead of silently treating it
as a no-op -- the failure mode that hid Immolate and Burning Pact+.
"""

# Potions the turn model scores. Keys map to effects Sim.drink() understands.
POTIONS = {
    "Fire Potion":       {"damage": (20, 40), "targeted": True},
    "Explosive Potion":  {"damage_all": (10, 20)},
    "Block Potion":      {"block": (12, 24)},
    "Energy Potion":     {"energy": (2, 4)},
    "Strength Potion":   {"strength": (2, 4)},
    # Flex Potion's Strength is lost at end of turn, which is after damage has
    # already been dealt, so within one turn it is just Strength.
    "Flex Potion":       {"strength": (5, 10)},
    "Dexterity Potion":  {"dexterity": (2, 4)},
    "Fear Potion":       {"vulnerable": (3, 6), "targeted": True},
    "Weak Potion":       {"weak": (3, 6), "targeted": True},
    # sts_lightspeed has this ternary the wrong way round (20 with Bark, 40
    # without); the game heals 20% and Sacred Bark doubles it, like every
    # other potion, so the sibling entries are the authority here.
    "Blood Potion":      {"heal_pct": (20, 40)},
    "Regen Potion":      {"regen": (5, 10)},
    "Heart of Iron":     {"metallicize": (6, 12)},
    "Essence of Steel":  {"plated_armor": (4, 8)},
    "Ghost in a Jar":    {"intangible": (1, 2)},
    "Ancient Potion":    {"artifact": (1, 2)},
    "Blessing of the Forge": {"upgrades_hand": True},
}

# Known potions whose effect this model cannot score in one turn: they draw or
# generate random cards, act across turns, or leave combat entirely.
UNSCOREABLE = {
    "Ambrosia", "Attack Potion", "Bottled Miracle", "Colorless Potion",
    "Cultist Potion", "Cunning Potion", "Distilled Chaos", "Duplication Potion",
    "Elixir", "Entropic Brew", "Essence of Darkness", "Fairy in a Bottle",
    "Focus Potion", "Fruit Juice", "Gambler's Brew", "Liquid Bronze",
    "Liquid Memories", "Poison Potion", "Potion of Capacity", "Power Potion",
    "Skill Potion", "Smoke Bomb", "Snecko Oil", "Speed Potion", "Stance Potion",
}


def value(effect, key, sacred_bark):
    return effect[key][1 if sacred_bark else 0]
