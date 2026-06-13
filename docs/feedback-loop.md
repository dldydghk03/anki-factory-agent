# Feedback Loop

The workflow treats every human correction as a potential training signal, but
not every correction becomes a global rule.

## Inputs

- generated cards
- human-edited cards
- review comments
- deck-level quality notes
- answer accuracy after study
- repeated failure patterns

## Review Labels

Each issue should be labeled with one primary failure type:

- weak cloze target
- missing foundation concept
- awkward phrasing
- repeated concept
- weak image cue
- poor spacing
- unsupported fact
- over-compressed exam reference
- lecture-profile mismatch

## Gold User Fixed Examples

`gold_user_fixed` examples are human edits that should become regression tests.
They are useful when they show a repeatable improvement:

- a better cloze target
- a clearer causal explanation
- a cleaner comparison structure
- a more natural wording pattern
- a better way to explain old exam references

The agent should compare future output against these examples and flag similar
failures.

## False Positive and False Negative Control

False positive:

- the reviewer flags a card as bad, but the card is acceptable for that lecture
  profile

False negative:

- the reviewer misses a card that is confusing, repetitive, or poorly targeted

The goal is not to reject every imperfect card. The goal is to catch cards that
will hurt learning efficiency.

## Metrics

Useful metrics include:

- percent of cards edited by the user
- percent of cards with cloze-target changes
- repeated concept count per deck
- missing foundation concept count
- image cue missing count
- post-study answer accuracy
- cards marked easy/hard after review
- regression count after a rule change

## Rule Promotion Gate

A correction can become a rule when:

1. it appears in more than one deck or source type
2. it improves learning clarity without adding unnecessary length
3. it does not overfit one subject
4. it can be tested with synthetic or de-identified examples
5. it reduces a tracked failure type

