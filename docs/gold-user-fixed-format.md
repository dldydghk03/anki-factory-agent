# Gold User Fixed Format

`gold_user_fixed` examples capture a human correction that should become a
regression signal. They should be synthetic or de-identified before publication.

## Required Fields

The public fixture uses the same review-event shape as
`schemas/review-event.schema.json`:

- `event_id`
- `deck_profile`
- `failure_type`
- `before`
- `after`
- `rule_candidate`
- `source_boundary`
- `notes` when helpful

## How to Write a Good Example

A useful example should show a repeatable improvement:

- weak cloze target changed to the concept that matters
- missing foundation concept added before a dense summary
- awkward source phrasing rewritten into natural study language
- repeated concept removed or split into distinct jobs
- image cue added so visual material supports the card

## Source Boundary

Before publishing, convert private examples into one of:

- synthetic: written from scratch
- de_identified: stripped of private details and source-specific phrasing
- aggregate_only: summarized as counts or failure types

Do not publish raw lecture text, real user logs, private deck exports, or
question-bank wording.

## Promotion Rule

A `gold_user_fixed` example can become a rule candidate when it improves at
least one tracked failure type and does not overfit one lecture or subject.

