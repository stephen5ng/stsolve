import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stsolve import frontier
from stsolve.state import parse

LOG = os.path.join(os.path.dirname(__file__), "..", "data", "states.jsonl")
states = [json.loads(l) for l in open(LOG) if l.strip()]

def find(floor, turn, mon_hp):
    for s in states:
        g = s.get("game_state") or {}
        cs = g.get("combat_state")
        if not cs: continue
        if g.get("floor") == floor and cs["turn"] == turn:
            if any(m["current_hp"] == mon_hp for m in cs["monsters"]):
                if cs["player"]["energy"] == max(3, cs["player"]["energy"]):
                    return s
    return None

for label, args in [("Guardian t2 (advised Bash+->PerfStrike->Strike = 37)", (16, 2, 225)),
                    ("Byrds t1 (advised Whirlwind x3 to strip Flight)",       (18, 1, 26)),
                    ("Gremlin Nob t2 (advised Berserk/Metallicize/PT+/Strike)",(12, 2, 62))]:
    s = find(*args)
    if s is None:
        print("!! state not found:", label); continue
    r = frontier(s)
    print("=" * 72); print(label)
    kw = parse(s)
    print("  energy=%s hp=%s block=%s  monsters=%s" % (
        kw["energy"], kw["hp"], kw["block"],
        [(m["name"], m["hp"], m["block"], m["intent_damage"]*m["intent_hits"]) for m in kw["monsters"] if not m["gone"]]))
    print("  hand:", [ (c["name"], c["cost"]) for c in s["game_state"]["combat_state"]["hand"] ])
    print("  sequences considered: %d" % r["considered"])
    for pt in r["frontier"][:6]:
        print("   dmg=%-4s hpLost=%-4s %s" % (pt["damage"], pt["hp_lost"], " -> ".join(pt["line"]) or "(end turn)"))
