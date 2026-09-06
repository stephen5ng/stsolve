#!/usr/bin/env python3
"""Test the damage model against every observed attack in the log.

Measurement notes (learned the hard way on v1):
  - Damage eats block first, so the observable is (block+hp) before minus after.
  - Overkill is invisible: a 32-damage Bludgeon into a 23-HP target reads as 23.
    So compare against the prediction CAPPED at the target's remaining pool.
  - Some monsters GAIN block during our own turn (Curl Up on first hit, the
    Guardian's Mode Shift). Those transitions can't be measured without knowing
    how much was gained, so they're reported separately rather than scored.
"""
import collections
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from transitions import load, build, combat, powers
from cards import ATTACKS, predict_damage


def main():
    states = load(sys.argv[1]) if len(sys.argv) > 1 else load()
    _, trans = build(states)
    ok = bad = 0
    contaminated = collections.Counter()
    failures = []
    per_card = collections.Counter()
    per_card_ok = collections.Counter()
    overkill = 0

    for t in trans:
        if t["kind"] != "play":
            continue
        card = t["detail"]["card"]
        if card not in ATTACKS:
            continue
        b, a = combat(t["before"]), combat(t["after"])
        if len(b["monsters"]) != len(a["monsters"]):
            continue
        deck = t["before"]["game_state"].get("deck", [])
        pp = powers(b["player"])
        energy = t["detail"]["energy_spent"]

        for mb, ma in zip(b["monsters"], a["monsters"]):
            if mb.get("is_gone"):
                continue
            pool_b = mb["block"] + mb["current_hp"]
            pool_a = ma["block"] + ma["current_hp"]
            obs = pool_b - pool_a
            if ma["block"] > mb["block"]:
                contaminated[card] += 1        # monster gained block mid-play
                continue
            if obs == 0:
                continue
            pred = predict_damage(card, energy, deck, pp, powers(mb))
            if pred is None:
                continue
            capped = min(pred, pool_b)
            if capped != pred:
                overkill += 1
            per_card[card] += 1
            if capped == obs:
                ok += 1
                per_card_ok[card] += 1
            else:
                bad += 1
                failures.append((card, mb["name"], obs, capped, pred, powers(mb), pp))

    total = ok + bad
    print("attack hits scored     : %d" % total)
    print("  model correct        : %d  (%.1f%%)" % (ok, 100.0 * ok / total if total else 0))
    print("  model wrong          : %d" % bad)
    print("  (of which overkill-capped: %d)" % overkill)
    print("  unscorable, target gained block: %d" % sum(contaminated.values()),
          dict(contaminated) or "")
    print()
    print("per card (correct/scored):")
    for c in sorted(per_card):
        mark = "" if per_card_ok[c] == per_card[c] else "   <-- MISMATCH"
        print("   %-18s %d/%d%s" % (c, per_card_ok[c], per_card[c], mark))
    if failures:
        print()
        print("mismatches:")
        for card, tgt, obs, capped, raw, mp, pp in failures:
            print("   %-16s vs %-16s observed=%-4s predicted=%-4s (raw %s)" % (card, tgt, obs, capped, raw))
            print("        target powers %s | player powers %s" % (mp, pp))


if __name__ == "__main__":
    main()
