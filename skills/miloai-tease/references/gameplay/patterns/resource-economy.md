# Resource Economy

## Design profile

- **Role:** Anchor or support pattern
- **Best for:** scarcity, planning, tradeoffs, earning, spending, upgrades
- **Typical scale:** phase / whole work
- **Can lead a phase:** Yes, when earning and spending are the main decisions
- **Player mainly:** acquire a limited resource, decide when and how to spend it, and live with the resulting future options
- **Combines well with:** `progression.md`, `map-exploration.md`, `roll-and-move-board.md`, `quiz-challenge.md`, `puzzle-challenge.md`, `save-resume.md`


A resource economy makes a numeric or countable resource matter across multiple decisions. The resource may represent currency, charges, energy, favors, tokens, materials, points, or another neutral budget. What makes it an economy is not the label—it is the repeated exchange between **earning, scarcity, spending, and future opportunity**.

## Core loop

```text
perform activity or accept consequence
→ gain / lose resource
→ encounter a spending decision
→ compare immediate benefit against later opportunity
→ buy, save, trade, or go without
→ future options change
```

If the resource is only a counter toward one threshold, use `progression.md`. If the player never chooses how to spend it, it is usually just state rather than an economy.

## Minimal state

```yaml
# milo.yaml
state:
  credits: 0
  rerollCharges: 0
  upgradeUnlocked: false
```

Use one primary currency unless multiple resources create genuinely different decisions. Avoid adding separate currencies only to decorate different sections of the tease.

## Earn and spend

```yaml
pages:
  reward:
    - set: credits += 2
    - say: You gained 2 credits.
    - goto: hub

  shop:
    - say: You have <eval>credits</eval> credits.
    - choice:
        - label: Buy a reroll for 3 credits
          commands:
            - if:
                condition: credits >= 3
                commands:
                  - set: credits -= 3
                  - set: rerollCharges += 1
                  - goto: shop-purchase-complete
                elseCommands:
                  - goto: shop-cannot-afford
        - label: Save the credits
          to: hub

  shop-purchase-complete:
    - say: Purchase complete.
    - goto: hub

  shop-cannot-afford:
    - say: You do not have enough credits.
    - goto: shop
```

Check affordability before subtracting the cost. Keep a purchase atomic: verify → spend → grant the benefit → leave or refresh the shop.

## Meaningful spending choices

A good sink changes what the player can do later. Typical effects include:

- avoid or soften a setback;
- reroll or redraw an uncertain result;
- buy a hint, clue, shortcut, or retry;
- unlock an optional route or event pool;
- improve future earning efficiency;
- restore a limited-use capability.

Avoid shops full of items whose effects are cosmetic to the gameplay unless cosmetics are explicitly the player's goal. The player should understand enough about costs and effects to make a real tradeoff.

## Scarcity and pacing

An economy only creates tension when supply and demand interact. Consider:

- expected resource earned per cycle;
- mandatory versus optional costs;
- whether saving has a future payoff;
- whether one purchase dominates every other option;
- whether the player can become permanently unable to progress.

Required progress should not depend on buying something after the resource can be irreversibly exhausted unless an alternate route exists.

## Caps, floors, and debt

Use explicit bounds when they matter:

```yaml
resource-cap-check:
  - if:
      credits >= 10: resource-cap
      else: hub

resource-cap:
  - set: credits = 10
  - goto: hub
```

Do not allow accidental negative balances. Negative resource values should exist only when debt itself is an intentional mechanic with defined consequences and recovery.

## Upgrades versus consumables

Keep these concepts separate:

- **Consumable:** spending creates a one-time use or immediate effect.
- **Permanent upgrade:** spending changes later rules for the rest of the session or work.
- **Unlock:** spending opens content or an option but may not improve power.

Permanent upgrades usually compose with `progression.md`; cross-session ownership may require `save-resume.md`.

## Shops are optional UI, not the economy itself

An economy can exist without a literal shop. A recurring choice such as “spend one charge to avoid this result or keep it for later” is still resource gameplay.

Likewise, a shop with unlimited money and no opportunity cost is mostly a menu. Decide whether the player is supposed to plan a budget or simply configure preferences; use `settings.md` for the latter.

## Composition guidance

- **Economy + quiz:** correct answers earn currency; hints or skips cost it.
- **Economy + puzzle:** clues, retries, or reveals consume a limited budget.
- **Economy + board/exploration:** locations or spaces provide income, costs, shops, or limited recovery options.
- **Economy + progression:** later tiers add new sinks, upgrades, or earning rules.
- **Economy + save/resume:** persist stable long-form balances and owned upgrades across sessions.

When resource use is only a small modifier to another anchor pattern, keep it lightweight. Promote it to the phase anchor only when the player's recurring question is genuinely “what should I spend, save, or trade?”

## Check

- Every resource is initialized and has a clear source and sink.
- Purchases verify affordability before spending.
- A transaction cannot grant the benefit twice through accidental re-entry.
- Required progress cannot be permanently soft-locked by ordinary spending.
- Costs and benefits are understandable before consequential decisions.
- Resource caps, floors, reset rules, and persistence are explicit when relevant.
- Multiple currencies exist only when they create distinct decisions.
- The economy changes future options instead of acting as a decorative score counter.
