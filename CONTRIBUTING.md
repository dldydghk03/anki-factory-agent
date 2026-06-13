# Contributing

Thanks for helping improve Anki Factory Agent.

This project is early and intentionally source-safe. Contributions should focus
on reusable workflow, synthetic examples, schemas, validation, and documentation.

## Contribution Scope

Good contributions include:

- card quality rules
- synthetic before and after examples
- review-event schemas
- validation scripts
- deck quality metrics
- privacy and source-boundary checks
- documentation improvements

Do not contribute:

- private lecture files
- copyrighted question-bank text
- real user review logs
- generated decks derived from non-public sources
- API keys, tokens, or private drive paths

## Workflow

1. Open or choose an issue.
2. Keep the change small and reviewable.
3. Use synthetic or de-identified examples only.
4. Explain the failure mode the change addresses.
5. Add validation when the change affects schemas or review data.

## Review Criteria

A change is ready when it:

- improves a reusable workflow rule or example
- avoids leaking private source material
- is understandable without access to private notes
- does not overfit one lecture, subject, or card style
- can be checked by another maintainer

## Writing Style

Prefer direct, testable language. Avoid claims that depend on private material
unless the public artifact contains enough synthetic evidence to review the
claim independently.

