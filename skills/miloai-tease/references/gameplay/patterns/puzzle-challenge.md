# Puzzle Challenge

## Design profile

- **Role:** Anchor or scene pattern
- **Best for:** deduction, discovery, clues, memory, experimentation, delayed payoff
- **Typical scale:** scene / phase
- **Can lead a phase:** Yes
- **Player mainly:** inspect information, derive or discover a solution, submit it, and use feedback to progress
- **Combines well with:** `retry-loop.md`, `timed-challenge.md`, `progression.md`, `map-exploration.md`, `resource-economy.md`


A puzzle challenge asks the player to solve something rather than merely endure an instruction or pick a preference. The solution may come from a riddle, code, ordering problem, observed detail, multi-step clue chain, spatial relation, or information gathered elsewhere in the tease.

## Core loop

```text
present goal and available evidence
→ inspect / remember / manipulate clues
→ form a solution
→ submit or commit to the solution
→ validate
→ reveal feedback, new clue, retry state, or next puzzle
```

The important design property is **inference**: the player should be able to connect supplied information to a solution. If success is mainly factual recall, use `quiz-challenge.md`. If the activity is mainly navigation, use `maze.md` or `map-exploration.md`.

## Minimal state

```yaml
# milo.yaml
state:
  puzzleAnswer: null
  puzzleAttempts: 0
  hintUsed: false
```

Short puzzles may need only the submitted answer. Add attempts, hint flags, discovered clues, or stage state only when they change later behavior.

## Free-response solution

```yaml
pages:
  puzzle-entry:
    - say: Three clues point to one four-letter code. Enter the code when ready.
    - prompt: puzzleAnswer
    - set: puzzleAttempts += 1
    - if:
        puzzleAnswer == "NOVA": puzzle-solved
        else: puzzle-not-solved

  puzzle-not-solved:
    - say: That does not fit all three clues.
    - choice:
        Try again: puzzle-entry
        Ask for a hint: puzzle-hint

  puzzle-hint:
    - set: hintUsed = true
    - say: Re-read the second clue and compare it with the first.
    - goto: puzzle-entry

  puzzle-solved:
    - say: The clues fit. The route opens.
    - goto: puzzle-complete
```

The code and clue text above are placeholders. The actual puzzle must provide enough information for the player to derive its answer.

## Multiple-stage puzzle

Longer puzzles are usually clearer as stages rather than one giant condition:

```text
discover clue A
→ solve gate 1
→ reveal clue B or change the environment
→ solve gate 2 using A + B
→ final solution
```

Each stage should produce new information, remove uncertainty, or alter the problem. Avoid making the player repeat a solved sub-puzzle solely to return to the current stage.

Use stable state for discoveries that need to survive navigation or revisits:

```yaml
state:
  foundClueA: false
  foundClueB: false
  puzzleStage: 1
```

When clue discovery is distributed across locations, compose with `map-exploration.md` or `maze.md` and let the puzzle own only the inference/checking logic.

## Hints and retries

A failed answer should normally do one of three things:

- give targeted feedback that narrows the search space;
- unlock an optional hint;
- allow a clean retry without replaying unrelated setup.

Repeatedly saying only “wrong” creates friction, not puzzle depth. If attempts are limited, make that limit visible or narratively legible before it becomes consequential.

Hints can carry a cost when scarcity is part of the intended experience. Read `resource-economy.md` if buying or spending for hints becomes a recurring strategic choice.

## External or physical puzzle work

A tease may ask the player to solve something outside the immediate Page UI, such as arranging physical items, recording a sequence, or using a supplied visual. The same design rules still apply:

- the required material must actually be available;
- the completion condition must be clear;
- the player must know how to return and submit the result;
- failure must not depend on inaccessible or unstated information.

Do not use an external website as a hidden dependency for a reusable pattern. Project-specific external resources belong in project content, not in this reference's core model.

## Puzzle fairness

Before treating a challenge as solvable, verify:

- every necessary clue is reachable before the answer is required;
- clues are internally consistent;
- there is one intended solution or all accepted solutions are handled;
- the answer checker accepts the intended representation;
- optional hints do not accidentally reveal information the player could never infer otherwise;
- retry does not erase clues the player is expected to remember unless that reset is intentional.

The puzzle can be difficult, but the reason for difficulty should be reasoning, observation, memory, or experimentation—not missing data.

## Composition guidance

- **Puzzle + retry loop:** each failed attempt changes feedback or available hints.
- **Puzzle + timed challenge:** solve under a deadline when urgency is part of the intended experience.
- **Puzzle + progression:** solved stages unlock later clue sets or persistent routes.
- **Puzzle + exploration:** clues are gathered from different locations before the final solve.
- **Puzzle + resource economy:** hints, retries, or clue reveals consume a limited resource.

Use `quiz-challenge.md` for a sequence of objectively scored questions. Use `self-control-challenge.md` when success is primarily behavioral compliance rather than finding a solution.

## Check

- The player can obtain every required clue before solution checking.
- Answer validation matches the intended representation and accepted solutions.
- Retry returns to the correct puzzle state without replaying unrelated content.
- Hints are reachable and do not create contradictory state.
- Multi-stage puzzles preserve completed stages when appropriate.
- Failure or attempt limits are communicated before they matter.
- The puzzle ends in a solved, failed, abandoned, or intentionally repeatable state.
