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
    from .cards import ATTACKS, BLOCKS
    from .sim import (POWERS, ENERGY_CARDS, DRAW_CARDS, ADDS_TO_HAND,
                      STRENGTH_CARDS, DEBUFF_ALL)
    known = set(ATTACKS) | set(BLOCKS) | set(POWERS) | set(ENERGY_CARDS) \
        | set(DRAW_CARDS) | set(ADDS_TO_HAND) \
        | set(STRENGTH_CARDS) | set(DEBUFF_ALL)
    unknown = sorted({c["name"] for c in cs["hand"]
                      if c["name"] not in known and c["cost"] >= 0})
    r = frontier(state)
    out.append("   (%d sequences)%s" % (
        r["considered"],
        "  !! SEARCH TRUNCATED -- frontier may be missing better lines"
        if r.get("truncated") else ""))
    if unknown:
        out.append("   !! UNMODELLED IN HAND: %s -- frontier is INCOMPLETE,"
                   % ", ".join(unknown))
        out.append("      these cards were treated as doing nothing")
    if r["lethal"]:
        out.append("   LETHAL: %s" % " -> ".join(r["lethal"]["line"]))
    zero = [p for p in r["frontier"] if p["hp_lost"] == 0]
    if not zero:
        out.append("   no line takes zero damage")
    for p in r["frontier"]:
        out.append("   dmg %-4d  hp -%-4d %s" % (
            p["damage"], p["hp_lost"], " -> ".join(p["line"]) or "(end turn)"))
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
