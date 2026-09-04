"""A deterministic model of one Slay the Spire turn.

Only the parts needed to score a turn are modelled: damage, block, the
handful of powers that change those numbers, and end-of-turn resolution.
Every number here is checked against real logged play by ``validate.py``.
"""
import copy

from .cards import (ATTACKS, BLOCKS, perfected_strike_damage,
                    SELF_DAMAGE, LIFESTEAL)

# Cards whose effect isn't just "deal damage" or "gain block".
POWERS = {"Metallicize": 3, "Berserk": 1}
STRENGTH_CARDS = {"Inflame": 2, "Inflame+": 3, "Flex": 2, "Flex+": 4}
# name -> (weak, vulnerable) applied to ALL enemies
DEBUFF_ALL = {"Shockwave": (3, 3), "Shockwave+": (5, 5)}
# Gain Strength only if the target is telegraphing an attack.
CONDITIONAL_STRENGTH = {"Spot Weakness": 3, "Spot Weakness+": 4}
DOUBLE_BLOCK = {"Entrench", "Entrench+"}
ENERGY_CARDS = {"Bloodletting": (2, 3), "Bloodletting+": (3, 3)}  # (energy, hp cost)
DRAW_CARDS = {"Shrug It Off": 1, "Shrug It Off+": 1, "Pommel Strike": 1, "Battle Trance": 3,
              "Master of Strategy": 3, "Warcry": 1, "Warcry+": 2}
# Cards that add unplayable junk to hand when played.
ADDS_TO_HAND = {"Power Through": 2, "Power Through+": 2}


class Sim:
    """Mutable turn state. Cheap to deep-copy, which is how search branches."""

    def __init__(self, energy, hp, block, player_powers, monsters, deck,
                 draw_pile=None, max_hp=None):
        self.energy = energy
        self.hp = hp
        self.max_hp = max_hp if max_hp is not None else hp
        self.block = block
        self.pp = dict(player_powers)
        self.monsters = copy.deepcopy(monsters)
        self.deck = deck
        self.draw_pile = list(draw_pile or [])
        self.damage_dealt = 0      # total, incl. damage eaten by block
        self.hp_damage = 0         # damage that actually removed HP
        self.self_damage = 0          # Sharp Hide, Bloodletting
        self.log = []

    def clone(self):
        s = Sim(self.energy, self.hp, self.block, self.pp, self.monsters,
                self.deck, self.draw_pile, self.max_hp)
        s.damage_dealt = self.damage_dealt
        s.hp_damage = self.hp_damage
        s.self_damage = self.self_damage
        s.log = list(self.log)
        return s

    # ---------------------------------------------------------------- helpers
    def alive(self):
        return [m for m in self.monsters if not m["gone"] and m["hp"] > 0]

    def _attack_damage(self, base, target):
        d = base + self.pp.get("Strength", 0)
        if "Weakened" in self.pp:
            d = int(d * 0.75)
        if "Vulnerable" in target["powers"]:
            d = int(d * 1.5)
        if target["powers"].get("Flight", 0) > 0:
            d = int(d * 0.5)
        return max(0, d)

    def _apply(self, target, dmg):
        """Damage eats block first, then HP. Returns (total, hp_removed)."""
        absorbed = min(target["block"], dmg)
        target["block"] -= absorbed
        rest = dmg - absorbed
        dealt = min(rest, target["hp"])
        target["hp"] -= dealt
        if target["hp"] <= 0:
            target["gone"] = True
        return absorbed + dealt, dealt

    @staticmethod
    def _on_attacked(target):
        """Reactive powers that fire when a target takes an attack.

        Malleable: gains block each time it is attacked, and the amount grows
        by 1 per trigger (it resets at the start of the enemy's own turn, so
        it does not carry across turns). This is why multi-hit cards are bad
        into Malleable and single big hits are good -- the exact opposite of
        Flight, where hit count is what matters.
        """
        mal = target["powers"].get("Malleable", 0)
        if mal:
            target["block"] += mal
            target["powers"]["Malleable"] = mal + 1

    # ------------------------------------------------------------- play a card
    def playable(self, card):
        return card["cost"] >= 0 and card["cost"] <= self.energy

    def play(self, card, target_idx=None):
        name, cost = card["name"], card["cost"]
        spend = self.energy if name == "Whirlwind" else cost
        self.energy -= spend
        self.log.append(name if target_idx is None else "%s->%d" % (name, target_idx))

        if name in SELF_DAMAGE:
            self.hp -= SELF_DAMAGE[name]
            self.self_damage += SELF_DAMAGE[name]

        if name in DOUBLE_BLOCK:
            self.block *= 2

        if name in CONDITIONAL_STRENGTH:
            # only pays off if something is actually telegraphing an attack
            if any(m["intent_damage"] > 0 for m in self.alive()):
                self.pp["Strength"] = (self.pp.get("Strength", 0)
                                       + CONDITIONAL_STRENGTH[name])

        if name in ENERGY_CARDS:
            gain, hp_cost = ENERGY_CARDS[name]
            self.energy += gain
            self.hp -= hp_cost
            self.self_damage += hp_cost

        if name in BLOCKS:
            b = BLOCKS[name]
            if "Frail" in self.pp:
                b = int(b * 0.75)
            self.block += b

        if name in STRENGTH_CARDS:
            self.pp["Strength"] = self.pp.get("Strength", 0) + STRENGTH_CARDS[name]

        if name in DEBUFF_ALL:
            weak, vuln = DEBUFF_ALL[name]
            for t in self.alive():
                if t["powers"].get("Artifact", 0) > 0:
                    t["powers"]["Artifact"] -= 1
                    continue
                t["powers"]["Vulnerable"] = vuln
                t["powers"]["Weakened"] = weak

        if name in POWERS:
            self.pp[name] = self.pp.get(name, 0) + POWERS[name]
            if name == "Berserk":
                self.pp["Vulnerable"] = self.pp.get("Vulnerable", 0) + 2

        if name in ATTACKS:
            base, hits, hits_all = ATTACKS[name]
            if name.startswith("Perfected Strike"):
                base = perfected_strike_damage(self.deck, name.endswith("+"))
            if name.startswith("Whirlwind"):
                hits = spend
            healed_this_card = 0
            targets = self.alive() if hits_all else (
                [self.monsters[target_idx]] if target_idx is not None else [])
            for _ in range(hits or 0):
                for t in list(targets):
                    if t["gone"]:
                        continue
                    total, hp = self._apply(t, self._attack_damage(base, t))
                    self.damage_dealt += total
                    self.hp_damage += hp
                    healed_this_card += hp
                    if t["powers"].get("Flight", 0) > 0:
                        t["powers"]["Flight"] -= 1
                    if not t["gone"]:
                        self._on_attacked(t)
            if name in LIFESTEAL:
                self.hp = min(self.max_hp, self.hp + healed_this_card)

            # Bash applies Vulnerable unless Artifact eats it
            if name.startswith("Bash"):
                for t in targets:
                    if t["powers"].get("Artifact", 0) > 0:
                        t["powers"]["Artifact"] -= 1
                    else:
                        t["powers"]["Vulnerable"] = 3 if name == "Bash+" else 2
            # Sharp Hide: 3 HP per ATTACK CARD played (verified, not per hit)
            for m in self.alive():
                sh = m["powers"].get("Sharp Hide", 0)
                if sh:
                    self.hp -= sh
                    self.self_damage += sh
        return self

    # ------------------------------------------------------- end of turn score
    def end_turn(self):
        """Resolve end of turn and return HP lost this turn (incl. self-damage)."""
        block = self.block + self.pp.get("Metallicize", 0)
        incoming = 0
        for m in self.alive():
            if m["intent_damage"] <= 0:
                continue
            dmg = m["intent_damage"] * m["intent_hits"]
            if "Weakened" in m["powers"]:
                dmg = int(dmg * 0.75)
            incoming += dmg
        # Vulnerable on YOU raises incoming by 50%. Berserk applies it to
        # yourself, so any line playing Berserk pays for it the same turn.
        if "Vulnerable" in self.pp:
            incoming = int(incoming * 1.5)
        taken = max(0, incoming - block)
        return self.self_damage + taken
