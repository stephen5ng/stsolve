"""Exhaustive search over one turn's legal play sequences.

Output is a Pareto frontier of (damage dealt, HP lost) rather than a single
"best" line -- which point on that frontier you want is a judgement call the
solver deliberately does not make for you.
"""
import itertools

from .sim import Sim, DRAW_CARDS, KNOWN_CARDS, EXHAUSTS_HAND
from .state import parse, hand as parse_hand, potions as parse_potions

MAX_SEQUENCES = 3000000


def _targets(sim, card):
    if not card["targeted"]:
        return [None]
    return [i for i, m in enumerate(sim.monsters) if not m["gone"] and m["hp"] > 0]


def _upgraded(cards):
    """Hand after Blessing of the Forge.

    Costs are left alone: under Snecko Eye the live cost is random anyway, and
    the model has no table of upgraded costs. That understates the handful of
    cards that get cheaper when upgraded.
    """
    out = []
    for c in cards:
        up = c["name"] + "+"
        if c["name"].endswith("+") or up not in KNOWN_CARDS:
            out.append(c)
        else:
            out.append(dict(c, name=up))
    return out


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
                nxt.use(card, tgt)
                nxt_rest = rest
                if card["name"] in EXHAUSTS_HAND:
                    nxt_rest = []           # Fiend Fire exhausted all of it
                elif card.get("upgrades_hand"):
                    nxt_rest = _upgraded(rest)
                rec(nxt, nxt_rest, seq + [(card, tgt)])

    rec(sim0, cards, [])
    return results, seen > MAX_SEQUENCES


def frontier(state, max_depth=6):
    """Pareto-optimal (damage_dealt, hp_lost, line) for this turn."""
    kw = parse(state)
    if kw is None:
        return None
    sim0 = Sim(**kw)
    potions = parse_potions(state)
    cards = parse_hand(state) + potions
    # Potions are free, so they would otherwise crowd out real cards at the
    # depth limit.
    lines, truncated = enumerate_lines(sim0, cards, max_depth + len(potions))

    scored = []
    for sim, seq in lines:
        hp_lost = sim.end_turn()
        killed_all = not sim.alive()
        scored.append({
            "damage": sim.hp_damage,
            "raw_damage": sim.damage_dealt,
            "hp_lost": hp_lost,
            "lethal": killed_all,
            "potions": sim.potions_used,
            "line": [("drink " if c.get("potion") else "") + (
                c["name"] if t is None else "%s->#%d %s" % (
                    c["name"], t,
                    sim.monsters[t].get("id") or sim.monsters[t]["name"]))
                     for c, t in seq],
            "draws": [c["name"] for c, _ in seq if c["name"] in DRAW_CARDS],
            # Index in the line, not the rendered string: a targeted draw like
            # Pommel Strike renders as "Pommel Strike->#0 Foo" and would never
            # match its own name.
            "first_draw": next((i for i, (c, _) in enumerate(seq)
                                if c["name"] in DRAW_CARDS), None),
        })

    front = _pareto(scored)
    lethal = min((r for r in scored if r["lethal"]),
                 key=lambda r: (r["potions"], r["hp_lost"]), default=None)
    return {"frontier": front, "considered": len(lines), "truncated": truncated,
            "lethal": lethal}


def _pareto(scored):
    """Maximise damage, minimise HP lost, minimise potions spent.

    Potions are a third axis rather than a free resource: a line that wins by
    two points of damage and a Fire Potion should not hide the line that keeps
    the potion. Grouping by potion count keeps the inner pass linear.
    """
    by_potions = {}
    for r in scored:
        by_potions.setdefault(r["potions"], []).append(r)

    candidates = []
    for group in by_potions.values():
        group.sort(key=lambda r: (-r["damage"], r["hp_lost"]))
        best = None
        for r in group:
            if best is None or r["hp_lost"] < best:
                candidates.append(r)
                best = r["hp_lost"]

    def dominated(r):
        return any(o is not r
                   and o["damage"] >= r["damage"]
                   and o["hp_lost"] <= r["hp_lost"]
                   and o["potions"] <= r["potions"]
                   and (o["damage"], -o["hp_lost"], -o["potions"])
                       != (r["damage"], -r["hp_lost"], -r["potions"])
                   for o in candidates)

    front = [r for r in candidates if not dominated(r)]
    front.sort(key=lambda r: (-r["damage"], r["hp_lost"], r["potions"]))
    return front
