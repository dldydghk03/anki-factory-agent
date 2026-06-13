# Chart Bible Case Study

Chart Bible is a structured knowledge-production workflow used as a second
example of the same agent pattern. The source domain is different from Anki
cards, but the maintenance problem is similar: collect messy material, extract
reusable structure, review for clarity, and promote repeated improvements into
rules.

## What Transferred to Anki Factory

The Chart Bible workflow reinforced several design patterns:

- separate raw source notes from publishable explanations
- turn repeated reviewer edits into style and structure rules
- keep examples small enough to audit
- distinguish core concepts from supporting details
- add a short cue before dense visual or tabular content
- track why a section was changed, not only that it changed

## Reusable Agent Pattern

Both workflows use the same loop:

```text
source material -> structured draft -> review -> user correction
                -> reusable rule -> regression example
```

## Why This Matters

Anki decks and structured chart guides both fail when the output is technically
correct but hard to learn from. The useful agent behavior is not just producing
text. It is maintaining a quality system that improves across repeated work.

## Public Boundary

This repository documents the reusable method. It does not publish private,
licensed, or user-specific source material from the original Chart Bible work.

