#!/usr/bin/env python3
"""Turn states.jsonl into (before, action, after) transitions.

The log is an append-only stream of every state CommunicationMod pushed.
Consecutive states differ by whatever happened in between -- usually one
card play. We infer the action from the diffs so each transition becomes a
testable claim: "playing card C in state S should produce state S'".
"""
import collections
import json
import os

LOG = __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "data", "states.jsonl")


def load(path=LOG):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def combat(state):
    """Return combat_state if this state is an in-combat one, else None."""
    g = state.get("game_state") or {}
    return g.get("combat_state")


def key(state):
    """Identity for dedupe: identical consecutive pushes are common."""
    g = state.get("game_state") or {}
    cs = g.get("combat_state") or {}
    p = cs.get("player") or {}
    return (
        g.get("floor"), cs.get("turn"), p.get("energy"), p.get("block"),
        g.get("current_hp"),
        tuple(sorted(c["uuid"] for c in cs.get("hand", []))),
        tuple((m["current_hp"], m["block"], m["is_gone"]) for m in cs.get("monsters", [])),
    )


def counter(cards):
    return collections.Counter(c["name"] for c in cards)


def monsters(cs):
    return [m for m in cs.get("monsters", []) if not m.get("is_gone")]


def powers(entity):
    return {p["name"]: p["amount"] for p in entity.get("powers", [])}


def infer_action(before, after):
    """What happened between two in-combat states?

    Returns (kind, detail). Kinds:
      play:<card>  -- exactly one card left hand and energy dropped
      endturn      -- turn number advanced
      unknown      -- anything we can't pin down
    """
    b, a = combat(before), combat(after)
    if b is None or a is None:
        return ("noncombat", None)
    if a["turn"] != b["turn"]:
        return ("endturn", (b["turn"], a["turn"]))

    hb, ha = counter(b["hand"]), counter(a["hand"])
    gone = hb - ha
    gained = ha - hb
    de = b["player"]["energy"] - a["player"]["energy"]

    if len(gone) == 1 and sum(gone.values()) == 1:
        name = next(iter(gone))
        return ("play", {"card": name, "energy_spent": de, "drew": dict(gained)})
    if not gone and not gained:
        return ("noop", None)
    return ("unknown", {"left_hand": dict(gone), "entered_hand": dict(gained), "denergy": de})


def build(states):
    states = [s for s in states if combat(s) is not None]
    # dedupe consecutive identical pushes
    dedup, last = [], None
    for s in states:
        k = key(s)
        if k != last:
            dedup.append(s)
            last = k
    trans = []
    for i in range(len(dedup) - 1):
        before, after = dedup[i], dedup[i + 1]
        kind, detail = infer_action(before, after)
        trans.append({"i": i, "kind": kind, "detail": detail,
                      "before": before, "after": after})
    return dedup, trans


if __name__ == "__main__":
    states = load()
    dedup, trans = build(states)
    print("raw states in log      :", len(states))
    print("in-combat, deduped     :", len(dedup))
    print("transitions            :", len(trans))
    print()
    kinds = collections.Counter(t["kind"] for t in trans)
    for k, n in kinds.most_common():
        print("  %-10s %d" % (k, n))
    print()
    plays = collections.Counter(t["detail"]["card"] for t in trans if t["kind"] == "play")
    print("single-card plays observed (%d distinct):" % len(plays))
    for name, n in plays.most_common():
        print("   %-18s %d" % (name, n))
