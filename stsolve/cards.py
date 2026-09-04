#!/usr/bin/env python3
"""Card damage model. Every number here is a claim to be tested against the log."""

# name -> (base_damage, hits, hits_all)
ATTACKS = {
    "Strike":           (6, 1, False),
    "Strike+":          (9, 1, False),
    "Bash":             (8, 1, False),
    "Bash+":            (10, 1, False),
    "Cleave":           (8, 1, True),
    "Headbutt":         (9, 1, False),
    "Twin Strike":      (5, 2, False),
    "Bludgeon":         (32, 1, False),
    "Carnage":          (20, 1, False),
    "Iron Wave":        (5, 1, False),
    "Wild Strike":      (12, 1, False),
    "Reckless Charge":  (7, 1, False),
    "Perfected Strike": (None, 1, False),   # 6 + 2 per "Strike" card in deck
    "Whirlwind":        (5, None, True),    # X hits, X = energy spent
    "Fiend Fire":       (7, None, False),   # X hits, X = cards exhausted from hand
    "Fiend Fire+":      (10, None, False),
    "Immolate":         (21, 1, True),      # also adds a Burn to the discard
    "Immolate+":        (28, 1, True),
    "Clash":            (14, 1, False),
    "Pommel Strike":    (9, 1, False),
    "Uppercut":         (13, 1, False),
    "Heavy Blade":      (14, 1, False),     # Strength counts 3x; not modelled
    "Pommel Strike+":   (10, 1, False),
    "Headbutt+":        (14, 1, False),
    "Uppercut+":        (13, 1, False),
    "Iron Wave+":       (7, 1, False),
    "Twin Strike+":     (7, 2, False),
    "Cleave+":          (11, 1, True),
    "Carnage+":         (28, 1, False),
    "Bludgeon+":        (42, 1, False),
    "Bash++":           (12, 1, False),
    "Whirlwind+":       (8, None, True),
    "Hemokinesis":      (15, 1, False),      # also costs you 2 HP
    "Hemokinesis+":     (18, 1, False),
    "Dramatic Entrance": (8, 1, True),
    "Hand of Greed":    (20, 1, False),
    "Reaper":           (4, 1, True),        # heals for HP damage dealt
    "Reaper+":          (5, 1, True),
    "Clash+":           (18, 1, False),
    "Wild Strike+":     (17, 1, False),
    "Perfected Strike+": (None, 1, False),
}

# name -> block gained
BLOCKS = {
    "Defend": 5, "Defend+": 8,
    "Shrug It Off": 8, "Shrug It Off+": 11,
    "Iron Wave": 5, "Iron Wave+": 7,
    "True Grit": 7, "True Grit+": 9,
    "Power Through": 15, "Power Through+": 20,
    "Flame Barrier": 12, "Flame Barrier+": 16, "Ghostly Armor+": 13,
    "Finesse": 2, "Finesse+": 4, "Sentinel": 5, "Sentinel+": 8,
}


def perfected_strike_damage(deck, upgraded=False):
    n = sum(1 for c in deck if "Strike" in c["name"])
    return 6 + (3 if upgraded else 2) * n


# Cards that cost you HP when played.
SELF_DAMAGE = {"Hemokinesis": 2, "Hemokinesis+": 2, "Offering": 6}

# Attacks that heal you for the HP damage they deal.
LIFESTEAL = {"Reaper", "Reaper+"}


def predict_damage(card, energy_spent, deck, player_powers, monster_powers):
    """Damage a single attack card deals to ONE monster, after modifiers."""
    name = card
    if name not in ATTACKS:
        return None
    base, hits, _all = ATTACKS[name]
    if name.startswith("Perfected Strike"):
        base = perfected_strike_damage(deck, name.endswith("+"))
    if name.startswith("Whirlwind"):
        hits = energy_spent
    if base is None or hits is None:
        return None

    strength = player_powers.get("Strength", 0)
    weak = "Weakened" in player_powers
    vuln = "Vulnerable" in monster_powers
    flight = monster_powers.get("Flight", 0) > 0

    total = 0
    for _ in range(hits):
        d = base + strength
        if weak:
            d = int(d * 0.75)
        if vuln:
            d = int(d * 1.5)
        if flight:
            d = int(d * 0.5)
        total += max(0, d)
    return total
