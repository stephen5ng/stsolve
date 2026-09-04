"""Print the turn frontier for the most recent logged state.

    python3 -m stsolve.cli [path/to/states.jsonl]

Designed to be run in a loop next to a live CommunicationMod listener, or
against a recorded log for post-hoc analysis.
"""
import json
import sys

from .solve import frontier
from .state import parse


def last_state(path):
    """The most recent state in the log, whatever it is."""
    last = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)
            except ValueError:
                continue
    return last


def latest_combat_state(path, must_be_current=True):
    """Most recent in-combat state.

    With must_be_current (the default, and what you want live), returns None
    unless the very last logged state is in combat -- otherwise you'd be shown
    a stale frontier from a fight that already ended.
    """
    if must_be_current:
        s = last_state(path)
        if s and (s.get("game_state") or {}).get("combat_state"):
            return s
        return None
    last = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
            except ValueError:
                continue
            if (s.get("game_state") or {}).get("combat_state"):
                last = s
    return last


def render(state):
    kw = parse(state)
    g = state["game_state"]
    cs = g["combat_state"]
    out = []
    mons = [m for m in kw["monsters"] if not m["gone"]]
    incoming = sum(m["intent_damage"] * m["intent_hits"] for m in mons)
    out.append("turn %s | HP %s/%s | energy %s | block %s | incoming %s" % (
        cs["turn"], g["current_hp"], g["max_hp"], kw["energy"], kw["block"], incoming))
    for idx, m in enumerate(kw["monsters"]):
        if m["gone"]:
            continue
        label = m["name"]
        if m.get("id") and m["id"] != m["name"]:
            label = "%s [%s]" % (m["name"], m["id"])
        out.append("   #%d %-26s %3d hp  %3d blk  %s" % (
            idx, label, m["hp"], m["block"],
            " ".join("%s%s" % (k, v) for k, v in m["powers"].items())))
    from .sim import KNOWN_CARDS
    from .potions import POTIONS, UNSCOREABLE
    unknown = sorted({c["name"] for c in cs["hand"]
                      if c["name"] not in KNOWN_CARDS and c["cost"] >= 0})
    usable = [p["name"] for p in g.get("potions", []) if p.get("can_use")]
    unknown_potions = sorted({n for n in usable if n not in POTIONS})
    r = frontier(state)
    out.append("   (%d sequences)%s" % (
        r["considered"],
        "  !! SEARCH TRUNCATED -- frontier may be missing better lines"
        if r.get("truncated") else ""))
    if unknown:
        out.append("   !! UNMODELLED IN HAND: %s -- frontier is INCOMPLETE,"
                   % ", ".join(unknown))
        out.append("      these cards were treated as doing nothing")
    if unknown_potions:
        why = ("known but not scoreable in one turn"
               if all(n in UNSCOREABLE for n in unknown_potions) else "unknown")
        out.append("   !! UNMODELLED POTION: %s (%s) -- treated as doing nothing"
                   % (", ".join(unknown_potions), why))
    if r["lethal"]:
        out.append("   LETHAL: %s" % " -> ".join(r["lethal"]["line"]))
    zero = [p for p in r["frontier"] if p["hp_lost"] == 0]
    if not zero:
        out.append("   no line takes zero damage")
    for p in r["frontier"]:
        # hp_lost goes negative when healing outweighs damage taken.
        hp = "hp %s%-4d" % ("-" if p["hp_lost"] >= 0 else "+", abs(p["hp_lost"]))
        out.append("   dmg %-4d  %s %s%s" % (
            p["damage"], hp,
            "" if not p["potions"] else "(%d potion%s) " % (
                p["potions"], "" if p["potions"] == 1 else "s"),
            " -> ".join(p["line"]) or "(end turn)"))
    return "\n".join(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    any_state = "--any" in sys.argv          # for post-hoc log analysis
    path = args[0] if args else "data/states.jsonl"
    s = latest_combat_state(path, must_be_current=not any_state)
    if s is None:
        print("not currently in combat")
        return 1
    print(render(s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
