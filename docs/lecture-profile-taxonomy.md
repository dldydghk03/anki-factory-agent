# Lecture Profile Taxonomy

The agent should classify the source material before choosing card style and
review rules. This keeps rules general instead of overfitting to one lecture.

## lecture_only

Source material is mainly lecture explanation without a strong exam-reference
structure.

Risks:

- over-summarizing paragraphs
- hiding low-value words
- missing causal links

Preferred card style:

- short foundation cards
- mechanism cards
- comparison cards only after terms are introduced

## exam_reference_heavy

Source material contains old exam references, recurring clues, or answer
patterns.

Risks:

- over-compressing old references
- listing unexplained terms
- treating an image cue as the main diagnosis

Preferred card style:

- preserve exam cues
- add one-line explanations for why a clue matters
- define axes before frequency rules or comparison tables

## image_heavy

Source material depends on radiology, pathology, ECG, charts, or other visual
clues.

Risks:

- image overlapping title text
- caption and explanation visually merging
- missing cue for what to inspect

Preferred card style:

- image cue first
- spacing after the image
- one visual task per card

## case_based

Source material is organized around patient scenarios or decision points.

Risks:

- hiding details that do not change the decision
- losing the diagnostic branch
- mixing multiple decisions in one card

Preferred card style:

- decision-point cloze
- short rationale after the answer
- separate cards for diagnosis, test choice, and management

## calculation_heavy

Source material requires formulas, thresholds, or numeric interpretation.

Risks:

- hiding a number without teaching the formula
- skipping units or denominator
- testing arithmetic when the goal is interpretation

Preferred card style:

- formula foundation card
- threshold interpretation card
- worked synthetic example when safe

## mixed

Source material combines lecture explanation, exam cues, images, and cases.

Risks:

- applying one global card style to all sections
- repeated concepts across source types
- inconsistent cloze targets

Preferred card style:

- classify each section locally
- use distinct card jobs
- consolidate repeated concepts during review

