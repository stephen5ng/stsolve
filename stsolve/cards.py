#!/usr/bin/env python3
"""Card damage model. Every number here is a claim to be tested against the log."""

# name -> (base_damage, hits, hits_all)
ATTACKS = {
    "Strike":           (6, 1, False),
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
}

# name -> block gained
BLOCKS = {
    "Defend": 5, "Shrug It Off": 8, "Iron Wave": 5,
    "True Grit": 7, "True Grit+": 9,
    "Power Through": 15, "Power Through+": 20,
    "Flame Barrier": 12, "Ghostly Armor+": 13,
}


def perfected_strike_damage(deck):
    n = sum(1 for c in deck if "Strike" in c["name"])
    return 6 + 2 * n


def predict_damage(card, energy_spent, deck, player_powers, monster_powers):
    """Damage a single attack card deals to ONE monster, after modifiers."""
    name = card
    if name not in ATTACKS:
        return None
    base, hits, _all = ATTACKS[name]
    if name == "Perfected Strike":
        base = perfected_strike_damage(deck)
    if name == "Whirlwind":
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
