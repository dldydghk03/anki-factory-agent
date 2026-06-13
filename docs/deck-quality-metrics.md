# Deck Quality Metrics

Deck quality should be measured at the level of learning friction, not only at
the level of factual correctness.

## Core Metrics

- `total_review_events`: total flagged cards or review notes
- `edited_card_rate`: edited cards divided by reviewed cards
- `cloze_target_change_count`: cards where the hidden answer changed
- `missing_foundation_concept_count`: cards that used terms before defining them
- `repeated_concept_count`: cards testing the same idea without a new purpose
- `image_cue_missing_count`: image cards without a clear visual cue
- `awkward_phrasing_count`: cards rewritten for readability

## Failure Counts

Track counts by `failure_type` from the review-event schema. This keeps the
report aligned with fixtures and validation.

## How to Use the Report

Use metrics to decide what to fix first:

1. high weak-cloze count means the agent is hiding the wrong target
2. high missing-foundation count means terms need earlier explanation
3. high repeated-concept count means the deck needs consolidation
4. high image-cue count means image formatting rules need stronger enforcement

## Public Reporting Boundary

Publish only synthetic or aggregate metrics. Do not publish private deck names,
lecture file names, raw student notes, or copied source text.

