"""Checks for the Silent card pool.

The model was built entirely during an Ironclad run, so every green card was
missing and the frontier scored it as zero. On floor 21 of the Silent run
twelve of fifteen distinct cards in the deck were unmodelled.

Every damage number here is confirmed against recorded play:
    python3 -m stsolve.validate_damage ~/SlayTheSpire/live/logs/states.jsonl

Run: python3 tests/test_silent.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stsolve.sim import Sim, KNOWN_CARDS, DRAW_CARDS


def monster(hp=100, powers=None, dmg=0, hits=1):
    return {"name": "Dummy", "id": "Dummy", "hp": hp, "block": 0, "gone": False,
            "powers": dict(powers or {}), "intent_damage": dmg,
            "intent_hits": hits}


def sim(energy=5, hp=53, max_hp=70, powers=None, monsters=None, relics=None):
    return Sim(energy, hp, 0, powers or {}, monsters or [monster()], [],
               max_hp=max_hp, relics=relics)


def card(name, cost=1):
    return {"name": name, "cost": cost, "targeted": True}


FAILURES = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILURES.append("%s: got %r want %r" % (label, got, want))
    print("  %s %-54s %r" % ("ok  " if ok else "FAIL", label, got))


print("the deck is no longer invisible")
deck = ["After Image", "Bane", "Choke", "Dagger Throw+", "Footwork", "Leg Sweep",
        "Neutralize", "Quick Slash", "Slice", "Strike", "Sucker Punch",
        "Survivor", "Terror", "Wraith Form+", "Defend"]
missing = sorted(c for c in deck if c not in KNOWN_CARDS)
check("every Silent ATTACK is now modelled",
      [c for c in ("Slice", "Bane", "Quick Slash", "Dagger Throw+",
                   "Sucker Punch") if c in missing], [])
check("what is left is block/utility and the power cards",
      missing, ["After Image", "Choke", "Terror", "Wraith Form+"])

print("\nattacks (all confirmed against the live log)")
for name, want in (("Slice", 6), ("Slice+", 9), ("Bane", 7), ("Bane+", 10),
                   ("Quick Slash", 8), ("Dagger Throw", 9), ("Dagger Throw+", 12),
                   ("Sucker Punch", 7), ("Backstab", 11), ("Endless Agony", 4)):
    s = sim()
    s.play(card(name, 0), 0)
    check("%-16s deals %d" % (name, want), s.hp_damage, want)

# Strike Dummy is +3 per HIT and keys off the NAME, so it must not fire on
# Silent attacks that merely happen to be attacks.
s = sim(relics={"Strike Dummy"})
s.play(card("Quick Slash", 1), 0)
check("Strike Dummy does not touch non-Strike cards", s.hp_damage, 8)

s = sim(relics={"Strike Dummy"})
s.play(card("Strike", 1), 0)
check("...but still fires on Strike itself", s.hp_damage, 9)

print("\nSucker Punch applies Weak, like Neutralize")
s = sim()
s.play(card("Sucker Punch", 1), 0)
check("Sucker Punch: 7 damage and Weak 1",
      (s.monsters[0]["hp"], s.monsters[0]["powers"].get("Weakened")), (93, 1))
s = sim()
s.play(card("Sucker Punch+", 1), 0)
check("Sucker Punch+: 9 damage and Weak 2",
      (s.monsters[0]["hp"], s.monsters[0]["powers"].get("Weakened")), (91, 2))

# Observed on floor 21: Looter at Vulnerable 99 took 13 from a 9-damage Strike
# and 9 from a 6-damage Slice -- the multiplier is per card, floored.
s = sim(monsters=[monster(hp=22, powers={"Vulnerable": 99})], relics={"Strike Dummy"})
s.play(card("Slice", 0), 0)
s.play(card("Strike", 1), 0)
check("Slice 9 + Strike 13 into Vulnerable kills a 22 HP Looter exactly",
      s.monsters[0]["gone"], True)

print("\ncyclers are card-neutral, not card-positive")
# DRAW_CARDS is what cli.py reads to tell you to play a cycler EARLY -- the
# draw costs the same whenever you play it, so playing it first is free
# information. That advice never fired for the Silent deck because neither
# cycler was in the table.
for name in ("Quick Slash", "Quick Slash+", "Dagger Throw", "Dagger Throw+"):
    check("%-16s is flagged as a draw card" % name, name in DRAW_CARDS, True)

print("\nblock and utility")
for name, want in (("Survivor", 8), ("Survivor+", 11), ("Deflect", 4),
                   ("Leg Sweep", 11), ("Leg Sweep+", 14), ("Backflip", 5)):
    s = sim()
    s.play(card(name, 1), None)
    check("%-16s blocks %d" % (name, want), s.block, want)

print("\nFootwork scales every block card behind it")
s = sim()
s.play(card("Footwork", 1), None)
check("Footwork grants Dexterity 2", s.pp.get("Dexterity"), 2)
s.play(card("Defend", 1), None)
check("...so a 5-block Defend blocks 7", s.block, 7)
s.play(card("Leg Sweep", 2), 0)
check("...and Leg Sweep blocks 13", s.block, 20)

s = sim()
s.play(card("Footwork+", 1), None)
check("Footwork+ grants Dexterity 3", s.pp.get("Dexterity"), 3)

print("\nLeg Sweep is block AND Weak")
s = sim()
s.play(card("Leg Sweep", 2), 0)
check("Leg Sweep applies Weak 2", s.monsters[0]["powers"].get("Weakened"), 2)
s = sim()
s.play(card("Leg Sweep+", 2), 0)
check("Leg Sweep+ applies Weak 3", s.monsters[0]["powers"].get("Weakened"), 3)

# The Hexaghost turn, reproduced exactly. Divider is 6 hits of curHp/12+1,
# locked in when Activate resolves -- at 62 HP that is 6 per hit, 36 total.
# Weak applies PER HIT, so floor(6*0.75)=4 per hit is 24, not floor(36*0.75).
# Observed: 20 block, 4 damage through, 62 -> 58.
s = sim(hp=62, monsters=[monster(hp=224, dmg=6, hits=6)])
s.play(card("Footwork", 1), None)
s.play(card("Leg Sweep", 2), 0)
s.play(card("Defend", 1), None)
check("Hexaghost Divider: 20 block built", s.block, 20)
check("...and Weak makes 6x6=36 land as 6x4=24, so 4 gets through",
      s.end_turn(), 4)

# Without the Weak the same block would have let 16 through -- the Weak was
# worth more than the block on that turn, which is why Leg Sweep beat a
# second Defend.
s = sim(hp=62, monsters=[monster(hp=224, dmg=6, hits=6)])
s.play(card("Footwork", 1), None)
s.play(card("Defend", 1), None)
s.play(card("Defend", 1), None)
s.play(card("Defend", 1), None)
check("three Defends instead: 21 block but no Weak, 15 through",
      s.end_turn(), 15)

print()
if FAILURES:
    print("%d FAILURE(S)" % len(FAILURES))
    for f in FAILURES:
        print("   " + f)
    raise SystemExit(1)
print("all Silent card checks passed")
