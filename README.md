# stsolve

A single-turn solver for Slay the Spire, and — more importantly — a way to
check that its rules model is actually correct.

Given a live game state from
[CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod), it
enumerates every legal sequence of card plays for the current turn and reports
the **Pareto frontier** of (damage dealt, HP lost). It deliberately does not
tell you which point on that frontier to pick — that's a judgement call about
the run, not arithmetic about the turn.

```
turn 3 | HP 70/80 | energy 3 | block 0 | incoming 20
   Spheric Guardian    12 hp    0 blk  Barricade-1 Artifact2
   (93 sequences)
   LETHAL: Bludgeon->Spheric Guardian
   dmg 12    hp -0    Bludgeon->Spheric Guardian
```

## Why the validator matters more than the solver

A solver that confidently prints wrong numbers is worse than no solver, because
the format makes it look authoritative. So the rules model is tested against
real recorded play rather than against anybody's memory of the rules.

`data/states.jsonl` contains 316 states from one real Act 1 clear, which yield
**193 transitions** — 138 single-card plays across 20 distinct cards. Every card
value in `cards.py` is checked against them:

```
$ python3 -m stsolve.validate_damage
attack hits scored     : 86
  model correct        : 85  (98.8%)
```

The single miss is a Duplication Potion doubling a Whirlwind (observed 40,
predicted 20) — an unmodelled potion, not a bad card value. Block cards score
32/32.

### Rules the log settled

These were all genuinely contested while playing, and the log decides them:

| Claim | Verdict | Evidence |
|---|---|---|
| Sharp Hide charges per attack **card**, not per hit | confirmed | Twin Strike (2 hits) → 3 damage; Whirlwind (3 hits) → 3 |
| Dazed is Ethereal and leaves the deck on its own | confirmed | 247 sightings in the exhaust pile; Wound and Slimed: zero |
| Spike Slime's Split fires at **end of turn**, not on crossing 50% | confirmed | The large slime sat at 18/64, well under the 32 threshold, un-split — then became 2×18 on the end-turn transition |
| Malleable gives block per attack, growing by 1 each trigger | **modelled, not yet validated** | check is in place and activates as soon as such a fight is recorded |
| `draw_pile` order in the protocol is real | **refuted** | drawn card matched top-of-pile in 2 of 14 draws. Contents are known; order is not |

That last one matters for design: draws are a known *distribution*, not a
deterministic lookup.

### Measurement bugs outnumbered model bugs 10:1

The first validation run reported 11 model errors. Ten were bugs in the
validator:

1. **Overkill is invisible.** 32 damage into a 23 HP target reads as 23.
   Compare against `min(prediction, block + hp)`.
2. **Targets gain block mid-play.** Curl Up and the Guardian's Mode Shift both
   trigger during *your* turn, so `block delta + hp delta` goes negative.
3. **Exhaust looks like a play.** True Grit+ removing a card from hand is
   indistinguishable from playing it, except energy doesn't move.

Had the search been written first, that broken measurement would have been used
to "fix" a correct damage model.

## Verified model

```
damage = base + Strength
       -> int(* 0.75) if you are Weak
       -> int(* 1.5)  if the target is Vulnerable
       -> int(* 0.5)  if the target has Flight
       -> block first, then HP

Strike 6   Bash 8   Bash+ 10   Cleave 8 (all)   Headbutt 9
Twin Strike 5x2     Bludgeon 32    Carnage 20
Perfected Strike 6 + 2 per deck card whose name contains "Strike"
Whirlwind 5 x (energy spent), hits all
```

Reactive powers that change the arithmetic:

    Flight      halves damage; stripped by hit COUNT -> multi-hit is good
    Malleable   target gains block per attack, +1 each trigger, resets on its
                turn -> multi-hit is bad, one big hit is good
    Sharp Hide  3 HP per attack CARD (not per hit)
    Artifact    absorbs the next debuff (so Bash's Vulnerable is wasted)

Note that Flight and Malleable pull in exactly opposite directions, which is
why the frontier ranks by **HP removed** rather than raw damage -- damage
absorbed by block a target just generated is not progress.

## Limitations (the honest list)

**It is a single-turn solver, and single-turn optimal is not always right.**
Two real cases from the recorded run:

- Against three Byrds it prefers a line dealing 19 damage over one dealing 18 —
  but the 18 strips **Flight from all three**, doubling every subsequent attack.
  Hit-count value is a next-turn payoff the solver cannot see.
- Against Gremlin Nob it correctly avoids Berserk (self-Vulnerable costs HP this
  turn) without knowing Berserk pays +1 energy for the rest of the fight.

**Some reactive enemy powers aren't modelled.** Gremlin Nob's Enrage (gains
Strength whenever you play a Skill) is invisible to the search, so it will
happily recommend Skills into it. Flight and Malleable *are* modelled.

**A few cards are left unmodelled on purpose.** Demon Form, Barricade and
Corruption are worth zero within a single turn and enormous across a fight, so
scoring them at their true single-turn value would be actively misleading. They
trip the INCOMPLETE warning instead, which is the honest output.

**Relic effects are invisible.** Strike Dummy (+3 to cards named "Strike") and
Pen Nib (every 10th attack deals double) both change real damage numbers and
neither is modelled -- and because the unknown-card check only inspects your
hand, relics don't trigger a warning either.

**Also out of scope:** anything multi-turn, card rewards, pathing, campfires,
shops, potions, and whether a fight is worth taking at all.

## Usage

```bash
python3 -m stsolve.cli data/states.jsonl     # frontier for the latest state
python3 -m stsolve.validate_damage           # check card values against the log
python3 -m stsolve.validate_mechanics        # check the contested rules
```

`observe.py` is the CommunicationMod listener that produces the log. Point
CommunicationMod's `command=` at it:

```
command=/usr/bin/python3 /path/to/observe.py
runAtGameStart=true
```

Note that CommunicationMod uses **stdout as its command channel**, so anything
your listener prints there is parsed as a game command. Log to a file instead.

## License

MIT
