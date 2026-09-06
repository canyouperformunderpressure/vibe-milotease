# Deck Draw

## Design profile

- **Role:** Anchor or modifier pattern
- **Best for:** finite randomness, anticipation, depletion, memory of prior draws, card-driven rounds
- **Typical scale:** scene / phase
- **Can lead a phase:** Yes
- **Player mainly:** draw from a finite set, resolve the drawn card, and continue with the remaining deck or reshuffle state
- **Combines well with:** `random-pool-control.md`, `progression.md`, `push-your-luck.md`, `resource-economy.md`, `save-resume.md`


A deck-draw pattern is different from a Lottery because previous draws change future probabilities. Cards leave the available deck, move to a discard state, enter a hand, or become otherwise unavailable until a defined reset.

## Core loop

```text
draw from remaining deck
→ remove or mark the drawn card
→ resolve its effect
→ discard / keep / consume it
→ draw again or end the round
→ reshuffle only when the rules say so
```

If every draw is independent and the same result may immediately repeat, use `lottery.md`. Use a deck when depletion, card memory, reshuffling, suits/categories, or a hand materially changes play.

## Minimal no-replacement deck with Page availability

For a small authored deck, enabled Pages can represent the remaining cards:

```yaml
# milo.yaml
state:
  cardsRemaining: 3
```

```yaml
pages:
  deck-draw:
    - if:
        cardsRemaining <= 0: deck-reshuffle
        else: deck-card-*

  deck-card-a:
    - disable: deck-card-a
    - set: cardsRemaining -= 1
    - say: Resolve card A.
    - goto: deck-after-card

  deck-card-b:
    - disable: deck-card-b
    - set: cardsRemaining -= 1
    - say: Resolve card B.
    - goto: deck-after-card

  deck-card-c:
    - disable: deck-card-c
    - set: cardsRemaining -= 1
    - say: Resolve card C.
    - goto: deck-after-card

  deck-after-card:
    - choice:
        Draw again: deck-draw
        Stop: deck-end

  deck-reshuffle:
    - enable: deck-card-*
    - set: cardsRemaining = 3
    - say: The discard pile is shuffled back into the deck.
    - goto: deck-draw

  deck-end:
    - end: true
```

Wildcard Goto selects from enabled matching Pages, so disabling a card Page makes a compact no-repeat deck. This form works best when each logical card has one Page and the deck is not enormous.

## Reshuffle policy

Define when unavailable cards return:

- only after every card is exhausted;
- at the end of each round;
- when a special card triggers it;
- never during the current phase;
- after only the discard pile reaches a threshold.

Do not silently re-enable cards whenever convenient. Reshuffling changes the player's expectations about what can appear next.

## Card categories and repeated copies

Cards may share a category while remaining separate deck entries. For example, three “minor” cards and one “major” card create a 3:1 composition without weighted replacement.

If logical duplicates need identical content, route multiple card Pages to one shared resolution Page after marking the drawn copy unavailable.

For simple weighted random selection where outcomes do not deplete, use `lottery.md` instead of simulating a deck with copies.

## Hand versus immediate resolution

There are two distinct forms:

- **Draw-and-resolve:** each card takes effect immediately, then leaves the deck.
- **Hand management:** drawn cards remain available to the player, can be chosen later, compared, combined, or discarded strategically.

The first form can often use Page availability alone. A genuine hand usually needs richer structured state than Milo scalar state provides; use native JavaScript structures only when the design actually requires them, and load the Milo IR/runtime references before implementing that state.

Do not call something a hand if the player never chooses among held cards.

## Deck state and re-entry

Card removal must happen once per draw. Put depletion at a stable point before routes that could loop back into the same card Page.

When a deck spans sessions, persist enough state to reconstruct the remaining/discarded cards. Read `save-resume.md`; do not save only `cardsRemaining` if the identity of the remaining cards matters.

## Composition guidance

- **Deck + push-your-luck:** each safe card increases pending value while dangerous cards remain in the shrinking deck.
- **Deck + resource economy:** spend a charge to redraw, peek, discard, or recover a card.
- **Deck + progression:** later stages add cards, remove easy cards, or change category composition.
- **Deck + random-pool control:** use only when additional cooldown/guarantee behavior is still needed beyond natural depletion.
- **Deck + save/resume:** persist exact deck/discard state for long-form card play.

Use `lottery.md` for independent draws. Use `random-encounters.md` when the player mostly receives unrelated events and the finite composition of the pool is not itself meaningful.

## Check

- A drawn card becomes unavailable exactly when intended.
- `cardsRemaining` matches the actual enabled deck when using the Page-availability model.
- The deck never attempts a wildcard draw when no matching card Page is enabled.
- Reshuffle timing is explicit and restores exactly the intended cards.
- Re-entry cannot consume the same logical card twice accidentally.
- Duplicate cards, categories, and special cards have deliberate probabilities based on deck composition.
- Persistent decks save card identity, not only a count, when identity affects future draws.
- The design truly needs finite/depleting randomness; otherwise prefer `lottery.md`.
