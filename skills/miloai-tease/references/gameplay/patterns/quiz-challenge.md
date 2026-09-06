# Quiz Challenge

## Design profile

- **Role:** Anchor or modifier pattern
- **Best for:** knowledge, recall, correctness pressure, streaks, escalating stakes
- **Typical scale:** scene / phase
- **Can lead a phase:** Yes
- **Player mainly:** answer objectively checkable questions and deal with the consequences of being right or wrong
- **Combines well with:** `progression.md`, `retry-loop.md`, `timed-challenge.md`, `resource-economy.md`, `push-your-luck.md`


A quiz challenge turns correctness into gameplay state. The core activity is not merely choosing dialogue: the player is presented with a question that has a defensible answer, commits to an answer, receives feedback, and then sees that result change score, streak, pressure, available routes, or later stakes.

## Core loop

```text
present question
→ player answers
→ evaluate correctness
→ update score / streak / consequence
→ change stakes or select next question
→ finish, retry, or continue
```

The question content may be factual recall, arithmetic, observation, memory from earlier scenes, or another objectively checkable task. If there is no meaningful right/wrong result, use an ordinary choice instead of presenting it as a quiz.

## Minimal state

```yaml
# milo.yaml
state:
  quizScore: 0
  quizStreak: 0
  questionsAnswered: 0
```

Track only values that change later behavior. A short three-question scene may need only `quizScore`; a longer challenge may also use streak, mistakes, or a current tier.

## Multiple-choice question

```yaml
pages:
  quiz-question-1:
    - say: Which value is equal to 6 × 7?
    - choice:
        - label: "42"
          commands:
            - set: quizScore += 1
            - set: quizStreak += 1
            - goto: quiz-correct
        - label: "36"
          commands:
            - set: quizStreak = 0
            - goto: quiz-wrong
        - label: "48"
          commands:
            - set: quizStreak = 0
            - goto: quiz-wrong

  quiz-correct:
    - set: questionsAnswered += 1
    - say: Correct.
    - goto: quiz-next

  quiz-wrong:
    - set: questionsAnswered += 1
    - say: That answer was not correct.
    - goto: quiz-next
```

The labels are placeholders. Real questions should have exactly one intended answer unless the design explicitly supports multiple accepted answers.

## Free-response question

Use Prompt when recalling or deriving an answer is more important than recognizing it from options:

```yaml
# milo.yaml
state:
  quizAnswer: null
```

```yaml
pages:
  quiz-free-response:
    - say: Enter the four-letter code you were shown earlier.
    - prompt: quizAnswer
    - if:
        quizAnswer == "NOVA": quiz-correct
        else: quiz-wrong
```

Free-response checking should match the intended challenge. Do not accidentally turn capitalization, punctuation, whitespace, or spelling trivia into the real difficulty unless that precision is part of the game.

For complex answer normalization, use explicit JavaScript only after loading the Milo IR/runtime references needed for the implementation.

## Score, streak, and stakes

These are different design levers:

- **Score** accumulates performance across independent questions.
- **Streak** rewards consecutive success and resets or falls on failure.
- **Mistakes / strikes** make a limited number of failures matter.
- **Tier** changes question difficulty or consequences after milestones.

Prefer one primary performance signal. Do not maintain score, streak, lives, rank, and a second hidden score unless they each alter decisions or routing.

Example escalation:

```yaml
quiz-next:
  - if:
      quizStreak >= 5: quiz-high-stakes
      questionsAnswered >= 10: quiz-finish
      else: quiz-question-*
```

The next question may come from a wildcard pool. Read `random-pool-control.md` when questions should not repeat, need weighting, or require guarantees.

## Sudden death and optional risk

A useful late-phase variation is to let the player keep accumulated value but choose whether to risk it on harder questions:

```text
safe checkpoint reached
→ offer stop / continue
→ continue raises consequence of a wrong answer
→ correct answers increase the pending reward
→ wrong answer loses or reduces the pending reward
```

When this stop-or-risk decision becomes the main activity, compose with `push-your-luck.md` rather than burying the risk model inside quiz-specific state.

## Question quality

The gameplay collapses if the answer key is ambiguous. Before authoring a question, verify:

- the prompt contains enough information to answer it;
- exactly one answer is defensible under the stated rules;
- distractors are plausible but actually wrong;
- the difficulty comes from the intended knowledge or reasoning, not accidental wording;
- a wrong result gives useful feedback or a meaningful consequence rather than arbitrary punishment.

For questions based on information introduced earlier in the tease, make sure the player had a fair opportunity to encounter and retain that information.

## Composition guidance

- **Quiz + timed challenge:** answer before a deadline.
- **Quiz + progression:** later milestones unlock harder question pools or alter consequences.
- **Quiz + resource economy:** correct answers earn a spendable resource, or hints cost one.
- **Quiz + push-your-luck:** the player may bank a streak/reward or risk it on another question.
- **Quiz + retry loop:** failure teaches or changes the next attempt instead of simply replaying the same prompt unchanged.

Use `dual-task-challenge.md` instead when the main difficulty is maintaining another action while answering. Use `puzzle-challenge.md` when the player primarily investigates clues, experiments, or derives a solution rather than answering a sequence of discrete questions.

## Check

- Every scored question has a clear answer rule.
- Correct and wrong routes both update state exactly once.
- Score, streak, mistakes, or tiers cannot drift because of re-entry.
- Required questions cannot repeat forever when the phase needs finite progress.
- Difficulty and consequences escalate intentionally rather than only by adding more questions.
- Free-response comparison is no stricter than the intended challenge.
- The quiz has an explicit finish, failure, checkpoint, or intentional repeatable state.
