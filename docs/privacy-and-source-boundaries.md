# Privacy and Source Boundaries

This project is designed to be public without exposing private study material.

## Do Not Publish

- raw lecture PDFs
- lecture transcripts
- private Google Drive paths
- real user correction logs
- copyrighted question-bank text
- identifiable student or instructor information
- full generated decks derived from non-public sources

## Safe to Publish

- workflow diagrams
- abstracted card quality rules
- synthetic examples
- de-identified review labels
- schemas
- aggregate metrics
- small examples written from scratch

## Source-Grounded Does Not Mean Source-Leaking

The agent can use private sources during a local run, but public artifacts should
only contain:

- non-reconstructive summaries
- synthetic examples
- general rules
- aggregate evaluation results

## Review Before Release

Before publishing a new example or fixture, check:

1. Can the original lecture, question, or user be reconstructed from this?
2. Does the example copy source wording?
3. Does the example contain private drive names or file names?
4. Is the educational point expressible with a synthetic example instead?

