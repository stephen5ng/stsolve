"""Parse a CommunicationMod game state into the simulator's inputs."""


def powers(entity):
    return {p["name"]: p["amount"] for p in entity.get("powers", [])}


def parse(state):
    """Return kwargs for Sim(), or None if this state isn't an in-combat turn."""
    g = state.get("game_state") or {}
    cs = g.get("combat_state")
    if not cs:
        return None
    p = cs["player"]
    monsters = []
    for m in cs["monsters"]:
        monsters.append({
            "name": m["name"],
            "id": m.get("id", ""),
            "hp": m["current_hp"],
            "block": m["block"],
            "gone": bool(m.get("is_gone")),
            "powers": powers(m),
            # move_adjusted_damage is -1 when the intent isn't an attack.
            "intent_damage": max(0, m.get("move_adjusted_damage", -1)),
            "intent_hits": m.get("move_hits", 1) or 1,
        })
    return {
        "energy": p["energy"],
        "hp": g["current_hp"],
        "block": p["block"],
        "player_powers": powers(p),
        "monsters": monsters,
        "deck": g.get("deck", []),
        "draw_pile": [c["name"] for c in cs.get("draw_pile", [])],
    }


def hand(state):
    """Playable hand as [{name, cost, targeted}]. Costs are live (Snecko-aware)."""
    cs = state["game_state"]["combat_state"]
    out = []
    for c in cs["hand"]:
        if c["cost"] < 0 and c["name"] != "Whirlwind":
            continue                      # unplayable (Wound, Dazed, Slimed)
        out.append({"name": c["name"], "cost": max(0, c["cost"]),
                    "targeted": c.get("has_target", False),
                    "uuid": c.get("uuid")})
    return out
