"""Checks for the potion model and the healing accounting it needed.

Run: python3 tests/test_potions.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stsolve.sim import Sim
from stsolve.solve import _upgraded


def monster(hp=100, powers=None, dmg=0, hits=1):
    return {"name": "Dummy", "id": "Dummy", "hp": hp, "block": 0, "gone": False,
            "powers": dict(powers or {}), "intent_damage": dmg,
            "intent_hits": hits}


def sim(energy=3, hp=50, max_hp=80, block=0, powers=None, monsters=None,
        bark=False):
    return Sim(energy, hp, block, powers or {}, monsters or [monster()], [],
               max_hp=max_hp, sacred_bark=bark)


def potion(name, targeted=False):
    return {"name": name, "cost": 0, "potion": True, "targeted": targeted}


def card(name, cost=1):
    return {"name": name, "cost": cost, "targeted": True}


FAILURES = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILURES.append("%s: got %r want %r" % (label, got, want))
    print("  %s %-52s %r" % ("ok  " if ok else "FAIL", label, got))


print("potion effects")
s = sim()
s.drink(potion("Fire Potion", True), 0)
check("Fire Potion deals 20", s.hp_damage, 20)

s = sim(monsters=[monster(powers={"Vulnerable": 2})])
s.drink(potion("Fire Potion", True), 0)
check("Fire Potion x1.5 into Vulnerable", s.hp_damage, 30)

s = sim(bark=True)
s.drink(potion("Fire Potion", True), 0)
check("Sacred Bark doubles Fire Potion", s.hp_damage, 40)

s = sim(monsters=[monster(hp=40), monster(hp=40)])
s.drink(potion("Explosive Potion"))
check("Explosive Potion hits everything", s.hp_damage, 20)

s = sim()
s.drink(potion("Block Potion"))
check("Block Potion gives 12 block", s.block, 12)

s = sim(energy=1)
s.drink(potion("Energy Potion"))
check("Energy Potion gives 2 energy", s.energy, 3)

print()
print("potions that change end-of-turn resolution")
s = sim(monsters=[monster(dmg=10, hits=1)])
check("baseline: 10 incoming", s.end_turn(), 10)

s = sim(monsters=[monster(dmg=10, hits=1)])
s.drink(potion("Regen Potion"))
check("Regen Potion heals 5 of it back", s.end_turn(), 5)

s = sim(monsters=[monster(dmg=30, hits=3)])
s.drink(potion("Ghost in a Jar"))
check("Intangible caps each hit at 1", s.end_turn(), 3)

s = sim(monsters=[monster(dmg=10, hits=1)])
s.drink(potion("Essence of Steel"))
check("Plated Armor blocks like block", s.end_turn(), 6)

print()
print("healing is only worth the room you have for it")
s = sim(hp=50, max_hp=80, monsters=[monster(dmg=10)])
s.drink(potion("Blood Potion"))
check("Blood Potion heals 20% of max HP", s.healed, 16)

s = sim(hp=80, max_hp=80, monsters=[monster(dmg=10)])
s.drink(potion("Blood Potion"))
check("...and nothing at full HP", s.healed, 0)

s = sim(hp=80, max_hp=80, monsters=[monster(hp=40)])
s.play(card("Reaper", 2), 0)
check("Reaper lifesteal is worthless at full HP", s.healed, 0)

s = sim(hp=40, max_hp=80, monsters=[monster(hp=40)])
s.play(card("Reaper", 2), 0)
check("...and worth its damage when hurt", s.healed, 4)

print()
print("Blessing of the Forge")
hand = [card("Strike"), card("Twin Strike"), card("Whirlwind", 0),
        card("Bludgeon+"), card("Burning Pact+")]
up = [c["name"] for c in _upgraded(hand)]
check("upgrades what the model knows, leaves the rest",
      up, ["Strike+", "Twin Strike+", "Whirlwind+", "Bludgeon+", "Burning Pact+"])

# Regression: Whirlwind+ is X-cost too. Matching the name exactly instead of by
# prefix made it spend 0 energy and therefore deal no damage at all.
s = sim(energy=3, monsters=[monster(hp=100), monster(hp=100)])
s.play(card("Whirlwind+", 0), None)
check("Whirlwind+ spends all energy (3 hits x 8 x 2 enemies)", s.hp_damage, 48)

print()
if FAILURES:
    print("%d FAILURE(S)" % len(FAILURES))
    for f in FAILURES:
        print("   " + f)
    raise SystemExit(1)
print("all potion checks passed")
