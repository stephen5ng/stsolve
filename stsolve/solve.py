"""Exhaustive search over one turn's legal play sequences.

Output is a Pareto frontier of (damage dealt, HP lost) rather than a single
"best" line -- which point on that frontier you want is a judgement call the
solver deliberately does not make for you.
"""
import itertools

from .sim import Sim, DRAW_CARDS
from .state import parse, hand as parse_hand

MAX_SEQUENCES = 200000


def _targets(sim, card):
    if not card["targeted"]:
        return [None]
    return [i for i, m in enumerate(sim.monsters) if not m["gone"] and m["hp"] > 0]


def enumerate_lines(sim0, cards, max_depth=6):
    """Yield (Sim, [(card, target)]) for every legal play sequence."""
    results = []
    seen = 0

    def rec(sim, remaining, seq):
        nonlocal seen
        seen += 1
        if seen > MAX_SEQUENCES:
            return
        results.append((sim, list(seq)))
        if len(seq) >= max_depth:
            return
        for i, card in enumerate(remaining):
            if not sim.playable(card):
                continue
            rest = remaining[:i] + remaining[i + 1:]
            for tgt in _targets(sim, card):
                nxt = sim.clone()
                nxt.play(card, tgt)
                rec(nxt, rest, seq + [(card, tgt)])

    rec(sim0, cards, [])
    return results


def frontier(state, max_depth=6):
    """Pareto-optimal (damage_dealt, hp_lost, line) for this turn."""
    kw = parse(state)
    if kw is None:
        return None
    sim0 = Sim(**kw)
    cards = parse_hand(state)
    lines = enumerate_lines(sim0, cards, max_depth)

    scored = []
    for sim, seq in lines:
        hp_lost = sim.end_turn()
        killed_all = not sim.alive()
        scored.append({
            "damage": sim.damage_dealt,
            "hp_lost": hp_lost,
            "lethal": killed_all,
            "line": [c["name"] if t is None else "%s->%s" % (c["name"], sim.monsters[t]["name"])
                     for c, t in seq],
            "draws": [c["name"] for c, _ in seq if c["name"] in DRAW_CARDS],
        })

    # Pareto: maximise damage, minimise hp_lost
    scored.sort(key=lambda r: (-r["damage"], r["hp_lost"]))
    best, front = None, []
    for r in scored:
        if best is None or r["hp_lost"] < best:
            front.append(r)
            best = r["hp_lost"]
    return {"frontier": front, "considered": len(lines),
            "lethal": next((r for r in scored if r["lethal"]), None)}
