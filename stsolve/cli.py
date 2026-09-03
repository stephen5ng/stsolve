"""Print the turn frontier for the most recent logged state.

    python3 -m stsolve.cli [path/to/states.jsonl]

Designed to be run in a loop next to a live CommunicationMod listener, or
against a recorded log for post-hoc analysis.
"""
import json
import sys

from .solve import frontier
from .state import parse


def latest_combat_state(path):
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
    for m in mons:
        out.append("   %-18s %3d hp  %3d blk  %s" % (
            m["name"], m["hp"], m["block"],
            " ".join("%s%s" % (k, v) for k, v in m["powers"].items())))
    r = frontier(state)
    out.append("   (%d sequences)" % r["considered"])
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
    path = sys.argv[1] if len(sys.argv) > 1 else "data/states.jsonl"
    s = latest_combat_state(path)
    if s is None:
        print("no in-combat state found in", path)
        return 1
    print(render(s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
