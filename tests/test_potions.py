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
        bark=False, relics=None, pen_nib=None):
    return Sim(energy, hp, block, powers or {}, monsters or [monster()], [],
               max_hp=max_hp, sacred_bark=bark, relics=relics,
               pen_nib_counter=pen_nib)


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

# Logged: Time Eater at Vulnerable 5 went 321 -> 301 on a Fire Potion.
s = sim(monsters=[monster(powers={"Vulnerable": 2})])
s.drink(potion("Fire Potion", True), 0)
check("Fire Potion ignores Vulnerable (20, not 30)", s.hp_damage, 20)

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
print("intent damage is a snapshot, not a base value")
# move_adjusted_damage already includes everything in effect when the intent
# was set. Re-applying those multipliers under-predicts the hit, which is the
# dangerous direction to be wrong in.
s = sim(monsters=[monster(dmg=7, hits=3, powers={"Weakened": 4})])
check("pre-existing Weak is not applied again", s.end_turn(), 21)

s = sim(hp=50, powers={"Vulnerable": 1}, monsters=[monster(dmg=26, hits=1)])
check("pre-existing player Vulnerable is not applied again", s.end_turn(), 26)

# Logged: a 7x3 intent, Weakened by Shockwave+ the same turn, landed as 6x3=18
# -- floor(7*0.75)=5 per hit, not int(21*0.75)=15 on the total. (The real hit
# was 6 because Time Warp had also just given +2 Strength, which is a separate
# unmodelled gap.)
s = sim(energy=3, monsters=[monster(hp=200, dmg=7, hits=3)])
s.play(card("Shockwave+", 1), None)
check("Weak applied THIS turn lands, and per hit", s.end_turn(), 15)

s = sim(monsters=[monster(dmg=10, hits=2)])
check("baseline: no Berserk", s.end_turn(), 20)
s = sim(energy=3, monsters=[monster(dmg=10, hits=2)])
s.play(card("Berserk", 0), None)
check("Berserk's own Vulnerable does land, per hit", s.end_turn(), 30)

print()
print("relics")
s = sim(energy=3, monsters=[monster(hp=500)])
s.play(card("Twin Strike", 1), 0)
check("Twin Strike without Strike Dummy", s.hp_damage, 10)

s = sim(energy=3, relics=["Strike Dummy"], monsters=[monster(hp=500)])
s.play(card("Twin Strike", 1), 0)
check("Strike Dummy is +3 per HIT, not per card", s.hp_damage, 16)

s = sim(energy=3, relics=["Strike Dummy"], monsters=[monster(hp=500)])
s.play(card("Bludgeon", 3), 0)
check("...and only on Strike-named cards", s.hp_damage, 32)

s = sim(energy=3, powers={"Pen Nib": 1}, monsters=[monster(hp=500)])
s.play(card("Strike", 1), 0)
check("Pen Nib doubles the attack", s.hp_damage, 12)
s.play(card("Strike", 1), 0)
check("...once, then it is spent", s.hp_damage, 12 + 6)

s = sim(energy=3, powers={"Pen Nib": 1, "Weakened": 1}, monsters=[monster(hp=500)])
s.play(card("Strike", 1), 0)
check("Pen Nib doubles BEFORE Weak (12*.75=9, not 4*2=8)", s.hp_damage, 9)

s = sim(energy=9, pen_nib=8, monsters=[monster(hp=500)])
s.play(card("Strike", 1), 0)
check("the attack that arms Pen Nib is not itself doubled", s.hp_damage, 6)
s.play(card("Strike", 1), 0)
check("...the next one is", s.hp_damage, 6 + 12)

# The killing blow: Pen Nib armed, Strength 11, six cards left after playing it.
s = sim(energy=3, powers={"Strength": 11, "Pen Nib": 1}, monsters=[monster(hp=500)])
s.hand_size = 7
s.play(card("Fiend Fire", 1), 0)
check("Pen Nib doubles every Fiend Fire instance (6 x 36)", s.hp_damage, 216)

print()
print("Fiend Fire and the powers that share a key")
s = sim(energy=3, monsters=[monster(hp=500)])
s.hand_size = 7                      # Fiend Fire plus 6 others
s.play(card("Fiend Fire", 1), 0)
check("Fiend Fire pays per card exhausted (6 x 7)", s.hp_damage, 42)
check("...and the hand is gone", s.hand_size, 0)

s = sim(energy=3, powers={"Strength": 11}, monsters=[monster(hp=500)])
s.hand_size = 7
s.play(card("Fiend Fire", 1), 0)
check("...with Strength on every instance (6 x 18)", s.hp_damage, 108)

s = sim(energy=3, monsters=[monster(dmg=10)])
s.play(card("Metallicize+", 2), None)
check("Metallicize+ grants Metallicize, not 'Metallicize+'",
      s.pp.get("Metallicize"), 4)
check("...so end_turn actually blocks with it", s.end_turn(), 6)

print()
print("Time Warp")
# Time Eater at Time Warp 9: the 3rd card ends the turn, and the +2 Strength
# it grants lands on that same turn's attack.
tw = lambda n, **kw: monster(hp=300, powers={"Time Warp": n}, **kw)
s = sim(energy=9, monsters=[tw(9, dmg=7, hits=3)])
for i in range(5):
    if s.playable(card("Strike", 1)):
        s.play(card("Strike", 1), 0)
check("turn ends after the 12th card", s.cards_played, 3)
check("...and only 3 got played", s.turn_ended, True)
check("Time Warp's +2 Strength hits the same turn", s.end_turn(), (7 + 2) * 3)

s = sim(energy=9, monsters=[tw(9, dmg=7, hits=3)])
s.drink(potion("Block Potion"))
s.drink(potion("Energy Potion"))
check("potions do not advance Time Warp", s.monsters[0]["powers"]["Time Warp"], 9)

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

print("Curl Up")
# Floor 1, Silent: FuzzyLouseDefensive 13 hp / Curl Up 7 and FuzzyLouseNormal
# 12 hp / Curl Up 5. Two Strikes, one each, took them to 7 and 6 -- so the
# damage lands and only then does the block go up.
s = sim(energy=3, monsters=[monster(hp=13, powers={"Curl Up": 7}),
                            monster(hp=12, powers={"Curl Up": 5})])
s.play(card("Strike"), 0)
s.play(card("Strike"), 1)
check("Curl Up does not blunt the hit that triggers it",
      [m["hp"] for m in s.monsters], [7, 6])
check("both louses are now sitting behind their block",
      [m["block"] for m in s.monsters], [7, 5])

# Piling everything into one target is the trap: the second Strike is eaten.
s = sim(energy=3, monsters=[monster(hp=13, powers={"Curl Up": 7})])
s.play(card("Strike"), 0)
s.play(card("Strike"), 0)
check("second Strike into the same louse is fully absorbed",
      s.monsters[0]["hp"], 7)
check("and it only chewed 6 off the 7 block", s.monsters[0]["block"], 1)

# Spent on the first trigger, not once per hit.
s = sim(energy=3, monsters=[monster(hp=40, powers={"Curl Up": 7})])
s.play(card("Twin Strike"), 0)
check("Curl Up fires once, not per hit", s.monsters[0]["block"], 2)
check("Curl Up is consumed", "Curl Up" in s.monsters[0]["powers"], False)

# CurlUpPower.onAttacked guards on damageAmount < currentHealth: a killing
# blow pays out nothing, which is why lethal math can ignore Curl Up entirely.
s = sim(energy=3, monsters=[monster(hp=6, powers={"Curl Up": 7})])
s.play(card("Strike"), 0)
check("a lethal hit never grants Curl Up block", s.monsters[0]["gone"], True)

# Malleable still works, and the two stack on the same trigger path.
s = sim(energy=3, monsters=[monster(hp=40, powers={"Malleable": 3,
                                                  "Curl Up": 7})])
s.play(card("Strike"), 0)
check("Malleable and Curl Up both fire", s.monsters[0]["block"], 10)

print()
if FAILURES:
    print("%d FAILURE(S)" % len(FAILURES))
    for f in FAILURES:
        print("   " + f)
    raise SystemExit(1)
print("all potion checks passed")
