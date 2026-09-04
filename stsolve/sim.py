"""A deterministic model of one Slay the Spire turn.

Only the parts needed to score a turn are modelled: damage, block, the
handful of powers that change those numbers, and end-of-turn resolution.
Every number here is checked against real logged play by ``validate.py``.
"""
import copy

from .cards import (ATTACKS, BLOCKS, perfected_strike_damage,
                    SELF_DAMAGE, LIFESTEAL)
from .potions import POTIONS, value as potion_value

# Cards whose effect isn't just "deal damage" or "gain block".
# name -> (power the game actually grants, amount). The upgraded card grants
# the same power, so both have to map onto the same key or end_turn misses it.
POWERS = {"Metallicize": ("Metallicize", 3), "Metallicize+": ("Metallicize", 4),
          "Berserk": ("Berserk", 1)}
# Cards that exhaust your whole hand when played.
EXHAUSTS_HAND = {"Fiend Fire", "Fiend Fire+"}
# Known cards left unscored on purpose: worth zero this turn and enormous
# across a fight, so scoring them honestly would be actively misleading.
# These warn rather than being silently treated as nothing.
DELIBERATELY_UNSCORED = {"Demon Form", "Demon Form+", "Barricade", "Barricade+",
                         "Corruption", "Corruption+", "Brutality", "Brutality+",
                         "Feel No Pain", "Feel No Pain+", "Dark Embrace",
                         "Dark Embrace+", "Juggernaut", "Juggernaut+"}
STRENGTH_CARDS = {"Inflame": 2, "Inflame+": 3, "Flex": 2, "Flex+": 4}
# name -> (weak, vulnerable) applied to ALL enemies
DEBUFF_ALL = {"Shockwave": (3, 3), "Shockwave+": (5, 5)}
# Attacks that debuff the single target they hit. name -> (weak, vulnerable).
# The debuff lands even when the damage is fully blocked -- it is not applied
# by the hit, it is applied by the card.
DEBUFF_TARGET = {"Neutralize": (1, 0), "Neutralize+": (2, 0)}
# Gain Strength only if the target is telegraphing an attack.
CONDITIONAL_STRENGTH = {"Spot Weakness": 3, "Spot Weakness+": 4}
DOUBLE_BLOCK = {"Entrench", "Entrench+"}
ENERGY_CARDS = {"Bloodletting": (2, 3), "Bloodletting+": (3, 3)}  # (energy, hp cost)
DRAW_CARDS = {"Shrug It Off": 1, "Shrug It Off+": 1, "Pommel Strike": 1, "Battle Trance": 3,
              "Master of Strategy": 3, "Warcry": 1, "Warcry+": 2}
# Cards that add unplayable junk to hand when played.
ADDS_TO_HAND = {"Power Through": 2, "Power Through+": 2}


# Every card name the model understands. cli.py warns about anything in hand
# that isn't here; the upgrade path checks it to know that "X+" is a real card.
KNOWN_CARDS = (set(ATTACKS) | set(BLOCKS) | set(POWERS) | set(ENERGY_CARDS)
               | set(DELIBERATELY_UNSCORED)
               | set(DRAW_CARDS) | set(ADDS_TO_HAND) | set(STRENGTH_CARDS)
               | set(DEBUFF_ALL) | set(DEBUFF_TARGET)
               | set(CONDITIONAL_STRENGTH) | set(DOUBLE_BLOCK)
               | set(SELF_DAMAGE) | set(LIFESTEAL))


class Sim:
    """Mutable turn state. Cheap to deep-copy, which is how search branches."""

    def __init__(self, energy, hp, block, player_powers, monsters, deck,
                 draw_pile=None, max_hp=None, sacred_bark=False, hand_size=0,
                 relics=None, pen_nib_counter=None):
        self.sacred_bark = sacred_bark
        self.energy = energy
        self.hp = hp
        self.max_hp = max_hp if max_hp is not None else hp
        self.block = block
        self.pp = dict(player_powers)
        self.monsters = copy.deepcopy(monsters)
        # An intent's move_adjusted_damage is a SNAPSHOT: it already accounts
        # for the monster's Strength, any Weak on the monster, and any
        # Vulnerable on you at the moment the intent was set. Re-applying those
        # multipliers at end of turn double-counts them and under-predicts the
        # hit. Only debuffs landed *after* the snapshot are missing from it, so
        # record what was already there.
        for m in self.monsters:
            m.setdefault("weak_at_snapshot", "Weakened" in m["powers"])
        self.vuln_at_snapshot = "Vulnerable" in self.pp
        self.deck = deck
        self.draw_pile = list(draw_pile or [])
        self.damage_dealt = 0      # total, incl. damage eaten by block
        self.hp_damage = 0         # damage that actually removed HP
        self.self_damage = 0          # Sharp Hide, Bloodletting
        self.healed = 0            # lifesteal and potions, capped at max HP
        self.potions_used = 0
        self.cards_played = 0
        self.turn_ended = False    # Time Warp can end your turn early
        # Every card in hand, including the unplayable ones -- Fiend Fire
        # exhausts Wounds and Slimed too, and is paid per card exhausted.
        self.hand_size = hand_size
        self.relics = set(relics or ())
        # Pen Nib counts attack CARDS. The game arms the doubling at 9 and
        # parks the counter at -1 until the armed attack is played.
        self.pen_nib_counter = pen_nib_counter
        self.log = []

    def clone(self):
        s = Sim(self.energy, self.hp, self.block, self.pp, self.monsters,
                self.deck, self.draw_pile, self.max_hp, self.sacred_bark,
                self.hand_size, self.relics, self.pen_nib_counter)
        s.damage_dealt = self.damage_dealt
        s.hp_damage = self.hp_damage
        s.self_damage = self.self_damage
        s.healed = self.healed
        s.potions_used = self.potions_used
        s.vuln_at_snapshot = self.vuln_at_snapshot
        s.cards_played = self.cards_played
        s.turn_ended = self.turn_ended
        s.log = list(self.log)
        return s

    # ---------------------------------------------------------------- helpers
    def alive(self):
        return [m for m in self.monsters if not m["gone"] and m["hp"] > 0]

    def _attack_damage(self, base, target, double=False):
        d = base + self.pp.get("Strength", 0)
        if double:
            # Pen Nib doubles after Strength and before Weak -- the order the
            # game's own damage calculation uses.
            d *= 2
        if "Weakened" in self.pp:
            d = int(d * 0.75)
        if "Vulnerable" in target["powers"]:
            d = int(d * 1.5)
        if target["powers"].get("Flight", 0) > 0:
            d = int(d * 0.5)
        return max(0, d)

    def _heal(self, amount):
        """Heal, and record only the part that isn't wasted against max HP.

        This is why Reaper scores as nothing at full HP: the lifesteal has
        nowhere to go, so it does not offset any damage taken.
        """
        gained = max(0, min(amount, self.max_hp - self.hp))
        self.hp += gained
        self.healed += gained

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
    def _on_attacked(target, dmg):
        """Reactive powers that fire when a target takes an attack.

        Malleable: gains block each time it is attacked, and the amount grows
        by 1 per trigger (it resets at the start of the enemy's own turn, so
        it does not carry across turns). This is why multi-hit cards are bad
        into Malleable and single big hits are good -- the exact opposite of
        Flight, where hit count is what matters.

        Curl Up: block once, on the first attack that connects, then the power
        is spent. ``dmg`` is the damage BEFORE the target's block, which is
        what CurlUpPower.onAttacked sees -- powers run before block is
        subtracted. The caller skips this whole method when the hit was
        lethal, which is the game's ``damageAmount < currentHealth`` guard:
        a killing blow never pays out Curl Up.

        The tactical consequence is that the card which triggers Curl Up gets
        full value and everything after it that turn hits the new block. Lead
        with your biggest attack, not a chip hit.
        """
        mal = target["powers"].get("Malleable", 0)
        if mal:
            target["block"] += mal
            target["powers"]["Malleable"] = mal + 1

        curl = target["powers"].get("Curl Up", 0)
        if curl and dmg > 0:
            target["block"] += curl
            del target["powers"]["Curl Up"]

    # ------------------------------------------------------------- play a card
    def playable(self, card):
        if self.turn_ended:
            return False
        return card["cost"] >= 0 and card["cost"] <= self.energy

    def _tick_time_warp(self):
        """Time Eater: every 12 cards YOU play, your turn ends and it gains 2
        Strength -- and that Strength lands on the attack resolving at the end
        of the very turn you triggered it. Potions do not count as cards.
        """
        for m in self.alive():
            if "Time Warp" not in m["powers"]:
                continue
            m["powers"]["Time Warp"] += 1
            if m["powers"]["Time Warp"] >= 12:
                m["powers"]["Time Warp"] = 0
                m["bonus_strength"] = m.get("bonus_strength", 0) + 2
                self.turn_ended = True

    def use(self, card, target_idx=None):
        """Play a card or drink a potion, whichever this entry is."""
        if card.get("potion"):
            return self.drink(card, target_idx)
        return self.play(card, target_idx)

    def drink(self, potion, target_idx=None):
        """Apply a potion. Drinking is free, so no energy is spent.

        Potion damage is not an Attack: it ignores Strength, your own Weak,
        AND the target's Vulnerable. Verified against logged play -- a Fire
        Potion into a Vulnerable-5 Time Eater dealt 20, not 30.
        """
        name = potion["name"]
        self.potions_used += 1
        self.log.append("drink %s" % name if target_idx is None
                        else "drink %s->%d" % (name, target_idx))
        eff = POTIONS.get(name)
        if eff is None:
            return self                      # unmodelled; the CLI warns
        v = lambda k: potion_value(eff, k, self.sacred_bark)

        if "energy" in eff:
            self.energy += v("energy")
        if "block" in eff:
            self.block += v("block")
        if "strength" in eff:
            self.pp["Strength"] = self.pp.get("Strength", 0) + v("strength")
        if "dexterity" in eff:
            self.pp["Dexterity"] = self.pp.get("Dexterity", 0) + v("dexterity")
        for power in ("metallicize", "plated_armor", "intangible", "artifact",
                      "regen"):
            if power in eff:
                key = {"metallicize": "Metallicize", "plated_armor": "Plated Armor",
                       "intangible": "Intangible", "artifact": "Artifact",
                       "regen": "Regen"}[power]
                self.pp[key] = self.pp.get(key, 0) + v(power)
        if "heal_pct" in eff:
            self._heal(self.max_hp * v("heal_pct") // 100)

        hit = []
        if "damage_all" in eff:
            hit = [(t, v("damage_all")) for t in self.alive()]
        elif "damage" in eff and target_idx is not None:
            hit = [(self.monsters[target_idx], v("damage"))]
        for t, base in hit:
            if t["gone"]:
                continue
            total, hp = self._apply(t, base)
            self.damage_dealt += total
            self.hp_damage += hp

        for key, power in (("vulnerable", "Vulnerable"), ("weak", "Weakened")):
            if key not in eff or target_idx is None:
                continue
            t = self.monsters[target_idx]
            if t["powers"].get("Artifact", 0) > 0:
                t["powers"]["Artifact"] -= 1
            else:
                t["powers"][power] = v(key)
        return self

    def play(self, card, target_idx=None):
        name, cost = card["name"], card["cost"]
        self.hand_size = max(0, self.hand_size - 1)
        self.cards_played += 1
        self._tick_time_warp()
        # X-cost: startswith, not ==, or Whirlwind+ silently spends 0 and
        # therefore deals nothing.
        spend = self.energy if name.startswith("Whirlwind") else cost
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
            b = BLOCKS[name] + self.pp.get("Dexterity", 0)
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
            key, amount = POWERS[name]
            self.pp[key] = self.pp.get(key, 0) + amount
            if name == "Berserk":
                self.pp["Vulnerable"] = self.pp.get("Vulnerable", 0) + 2

        if name in ATTACKS:
            base, hits, hits_all = ATTACKS[name]
            if name.startswith("Perfected Strike"):
                base = perfected_strike_damage(self.deck, name.endswith("+"))
            if "Strike Dummy" in self.relics and "Strike" in name:
                # +3 per HIT, not per card: a 2-hit Twin Strike killed a 16 HP
                # Darkling, which 5+5+3 could not have done.
                base += 3
            if name.startswith("Whirlwind"):
                hits = spend
            if name in EXHAUSTS_HAND:
                hits = self.hand_size
            healed_this_card = 0
            pen_nib = bool(self.pp.pop("Pen Nib", 0))
            targets = self.alive() if hits_all else (
                [self.monsters[target_idx]] if target_idx is not None else [])
            for _ in range(hits or 0):
                for t in list(targets):
                    if t["gone"]:
                        continue
                    raw = self._attack_damage(base, t, double=pen_nib)
                    total, hp = self._apply(t, raw)
                    self.damage_dealt += total
                    self.hp_damage += hp
                    healed_this_card += hp
                    if t["powers"].get("Flight", 0) > 0:
                        t["powers"]["Flight"] -= 1
                    if not t["gone"]:
                        self._on_attacked(t, raw)
            if self.pen_nib_counter is not None:
                self.pen_nib_counter += 1
                if self.pen_nib_counter == 9:
                    self.pp["Pen Nib"] = 1
                    self.pen_nib_counter = -1
            if name in EXHAUSTS_HAND:
                self.hand_size = 0
            if name in LIFESTEAL:
                self._heal(healed_this_card)

            # Bash applies Vulnerable unless Artifact eats it
            if name.startswith("Bash"):
                for t in targets:
                    if t["powers"].get("Artifact", 0) > 0:
                        t["powers"]["Artifact"] -= 1
                    else:
                        t["powers"]["Vulnerable"] = 3 if name == "Bash+" else 2
            if name in DEBUFF_TARGET:
                weak, vuln = DEBUFF_TARGET[name]
                for t in targets:
                    if t["powers"].get("Artifact", 0) > 0:
                        t["powers"]["Artifact"] -= 1
                        continue
                    if weak:
                        t["powers"]["Weakened"] = (
                            t["powers"].get("Weakened", 0) + weak)
                    if vuln:
                        t["powers"]["Vulnerable"] = (
                            t["powers"].get("Vulnerable", 0) + vuln)
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
        block = (self.block + self.pp.get("Metallicize", 0)
                 + self.pp.get("Plated Armor", 0))
        if self.pp.get("Intangible", 0):
            # Intangible caps every instance of damage at 1, after all other
            # modifiers, so hit count is the only thing that matters.
            incoming = sum(m["intent_hits"] for m in self.alive()
                           if m["intent_damage"] > 0)
        else:
            incoming = 0
            new_vuln = "Vulnerable" in self.pp and not self.vuln_at_snapshot
            for m in self.alive():
                if m["intent_damage"] <= 0:
                    continue
                # Strength gained after the snapshot has to be scaled by the
                # multipliers the snapshot already baked in, then the whole
                # thing by any that landed since.
                bonus = m.get("bonus_strength", 0)
                if bonus:
                    if m["weak_at_snapshot"]:
                        bonus = int(bonus * 0.75)
                    if self.vuln_at_snapshot:
                        bonus = int(bonus * 1.5)
                # Both multipliers apply per hit, not to the total: a 7x3
                # intent at Strength 2 under Weak landed as 6x3=18, not
                # int(27*0.75)=20.
                per_hit = m["intent_damage"] + bonus
                if "Weakened" in m["powers"] and not m["weak_at_snapshot"]:
                    per_hit = int(per_hit * 0.75)
                if new_vuln:
                    per_hit = int(per_hit * 1.5)
                incoming += per_hit * m["intent_hits"]
        taken = max(0, incoming - block)
        self._heal(self.pp.get("Regen", 0))
        return self.self_damage + taken - self.healed
