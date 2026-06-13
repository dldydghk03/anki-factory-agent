# Security Policy

## Supported Scope

This repository currently contains public documentation, schemas, and synthetic
examples for an Anki deck generation workflow.

Security review is in scope for:

- source leakage risks
- accidental inclusion of private files
- prompt-injection-sensitive workflow design
- schema validation issues
- unsafe handling of generated review logs
- examples that could reconstruct private source material

## Out of Scope

Do not test or submit private source material, private Google Drive links,
credentials, paid question-bank text, or personal information.

## Reporting a Vulnerability

Open a private security advisory if available, or contact the maintainer through
GitHub with a minimal description of the issue. Do not include secrets or private
learning materials in the report.

For public issues, use synthetic examples that demonstrate the problem without
revealing non-public sources.

## Expected Response

For this early-stage project, the maintainer will prioritize:

1. removing leaked private material
2. fixing source-boundary documentation gaps
3. tightening schemas and validation
4. adding regression examples for the issue

