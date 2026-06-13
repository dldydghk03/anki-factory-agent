# Anki Factory Agent

Anki Factory Agent is an early public specification for a source-grounded study
material production workflow. It turns lecture notes, exam-style prompts,
review logs, and human corrections into Anki cards that are easier to study,
audit, and improve over time.

This repository does not publish private lectures, drive files, or real student
materials. It contains the reusable structure, quality rules, review loop, and
synthetic examples behind the workflow.

## Why This Exists

Most AI-generated study cards fail in predictable ways:

- they summarize instead of testing one clear recall target
- they hide numbers or wording that are less important than the concept
- they introduce terms before defining them
- they repeat the same concept across several cards
- they attach images without enough visual spacing or a useful cue
- they preserve awkward source phrasing instead of producing readable cards

This project treats Anki deck generation as a maintainable production workflow,
not a one-shot prompt.

## Current Scope

The current workflow is designed around medical study materials, especially
lecture-heavy and exam-reference-heavy decks. The rules are written to stay
general enough for other subjects:

- lecture-only decks
- exam-reference-heavy decks
- image-heavy decks
- case-based decks
- calculation-heavy decks
- mixed lecture and question-bank decks

The agent should infer the lecture profile first, then select the right card
style and review rules for that profile.

## Core Workflow

1. Collect bounded source context.
2. Classify the lecture profile.
3. Draft cards with source-grounded recall targets.
4. Run readability, duplication, and cloze-quality checks.
5. Compare against human-edited examples.
6. Promote recurring fixes into reusable rules.
7. Track review outcomes and regressions.

```text
sources -> profile -> draft cards -> review rules -> human fixes
        -> gold examples -> metrics -> rule updates -> next deck
```

## Repository Layout

```text
docs/
  card-quality-rules.md       Reusable rules for card writing and review
  feedback-loop.md            Review, correction, and metric workflow
  chart-bible-case-study.md   Lessons from a structured Chart Bible workflow
  privacy-and-source-boundaries.md

examples/
  synthetic-card-before-after.md
  synthetic-review-events.jsonl

schemas/
  review-event.schema.json
```

## Design Principles

- Source-grounded first: cards must be traceable to the provided material.
- One card, one job: each card should test one meaningful recall target.
- Concept before detail: define required terms before using them as clues.
- Hide the decision point: cloze deletions should target the concept that
  changes the answer, not a less meaningful number or filler phrase.
- Preserve useful exam cues: old exam references should be clarified, not
  blindly compressed.
- Avoid subject overfitting: a good endocrine rule must not break cardiology,
  nephrology, image-based lectures, or calculation decks.
- Learn from corrections: repeated human edits become candidate rules only
  after they show broader value.

## Public Status

This is an early public repository created to document and open-source the
workflow. The next implementation steps are:

- add a small card-review CLI
- add fixtures for different lecture profiles
- add regression checks for awkward phrasing, repeated concepts, and weak
  cloze targets
- add a lightweight report for deck-level quality metrics

## Intended Use of Codex

Codex is useful here as a maintainer workflow assistant:

- drafting and reviewing card rules
- finding regressions across generated decks
- converting user corrections into test cases
- checking whether a new rule overfits one lecture style
- maintaining schemas, examples, and documentation
- preparing release-quality public artifacts without exposing private sources

