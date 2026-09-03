#!/usr/bin/env python3
"""Test the specific rules claims made during the run, against logged play."""
import collections
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from transitions import load, build, combat, powers
from cards import ATTACKS, BLOCKS

states = load()
dedup, trans = build(states)


def hdr(t):
    print("\n" + "=" * 68); print(t); print("=" * 68)


# ---------------------------------------------------------------- BLOCK MODEL
hdr("CLAIM: block = card value, reduced 25% (floored) by Frail")
ok = bad = 0
for t in trans:
    if t["kind"] != "play":
        continue
    c = t["detail"]["card"]
    if c not in BLOCKS:
        continue
    b, a = combat(t["before"]), combat(t["after"])
    obs = a["player"]["block"] - b["player"]["block"]
    pp = powers(b["player"])
    pred = BLOCKS[c]
    if "Frail" in pp:
        pred = int(pred * 0.75)
    flag = "ok" if pred == obs else "MISMATCH"
    if pred == obs:
        ok += 1
    else:
        bad += 1
        print("  %-8s %-16s observed=%-3s predicted=%-3s frail=%s" % (
            flag, c, obs, pred, "Frail" in pp))
print("  block plays: %d correct, %d wrong" % (ok, bad))


# ------------------------------------------------------------ SHARP HIDE RATE
hdr("CLAIM: Sharp Hide costs 3 HP per ATTACK CARD, not per hit")
rows = []
for t in trans:
    if t["kind"] != "play":
        continue
    c = t["detail"]["card"]
    if c not in ATTACKS:
        continue
    b, a = combat(t["before"]), combat(t["after"])
    sh = [m for m in b["monsters"] if not m.get("is_gone") and powers(m).get("Sharp Hide")]
    if not sh:
        continue
    hp_lost = t["before"]["game_state"]["current_hp"] - t["after"]["game_state"]["current_hp"]
    hits = ATTACKS[c][1]
    if c == "Whirlwind":
        hits = t["detail"]["energy_spent"]
    rows.append((c, hits, hp_lost, powers(sh[0])["Sharp Hide"]))
for c, hits, lost, amt in rows:
    verdict = "per-card" if lost == amt else ("per-hit" if lost == amt * (hits or 1) else "?")
    print("  %-16s hits=%-3s HP lost=%-3s SharpHide=%s  -> %s" % (c, hits, lost, amt, verdict))
if not rows:
    print("  no data")


# -------------------------------------------------------------- DAZED / WOUND
hdr("CLAIM: Dazed is Ethereal (exhausts from hand); Wound is not")
seen = collections.Counter()
for s in dedup:
    cs = combat(s)
    for pile in ("hand", "draw_pile", "discard_pile", "exhaust_pile"):
        for c in cs.get(pile, []):
            if c["name"] in ("Dazed", "Wound", "Slimed"):
                seen[(c["name"], pile, c.get("ethereal"))] += 1
for (name, pile, eth), n in sorted(seen.items()):
    print("  %-7s in %-13s ethereal=%-5s  seen %d times" % (name, pile, eth, n))

print("\n  Dazed reaching the exhaust pile is the test -- an Ethereal card")
print("  discarded from hand would appear in discard_pile instead.")


# ------------------------------------------------------------- SPLIT TIMING
hdr("CLAIM: Spike Slime (L) Split fires at END of turn, not on crossing 50%")
for i, t in enumerate(trans):
    b, a = combat(t["before"]), combat(t["after"])
    names_b = [m["name"] for m in b["monsters"] if not m.get("is_gone")]
    names_a = [m["name"] for m in a["monsters"] if not m.get("is_gone")]
    if names_b != names_a and any("Slime" in n for n in names_b + names_a):
        print("  transition kind=%s (%s)" % (t["kind"], t["detail"]))
        for m in b["monsters"]:
            if not m.get("is_gone"):
                print("    BEFORE %-18s %s/%s" % (m["name"], m["current_hp"], m["max_hp"]))
        for m in a["monsters"]:
            if not m.get("is_gone"):
                print("    AFTER  %-18s %s/%s" % (m["name"], m["current_hp"], m["max_hp"]))


# ---------------------------------------------------------------- MALLEABLE
hdr("CLAIM: Malleable gives the target block per attack, amount +1 each time")
rows = 0
for t in trans:
    if t["kind"] != "play":
        continue
    c = t["detail"]["card"]
    if c not in ATTACKS:
        continue
    b, a = combat(t["before"]), combat(t["after"])
    for mb, ma in zip(b["monsters"], a["monsters"]):
        pw_b, pw_a = powers(mb), powers(ma)
        if "Malleable" not in pw_b:
            continue
        rows += 1
        hits = t["detail"]["energy_spent"] if c == "Whirlwind" else ATTACKS[c][1]
        # each hit should add the current amount, then bump it by 1
        amt = pw_b["Malleable"]
        expect_gain = sum(amt + i for i in range(hits or 1))
        expect_amt = amt + (hits or 1)
        print("  %-16s hits=%-2s  block %3s->%-3s (net %+d)  Malleable %s->%s"
              % (c, hits, mb["block"], ma["block"],
                 ma["block"] - mb["block"], amt, pw_a.get("Malleable")))
        print("      predicted: block +%d before absorption, Malleable -> %d"
              % (expect_gain, expect_amt))
if rows == 0:
    print("  no Malleable data logged yet -- this check activates once a")
    print("  Snake Plant (or similar) fight is recorded.")
