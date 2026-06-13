# Release Checklist

Use this checklist before publishing examples, fixtures, or releases.

## Source Safety

- [ ] No raw lecture PDFs, audio, transcripts, or deck exports are included.
- [ ] No private Google Drive paths, local machine paths, or user logs are included.
- [ ] No credentials, API keys, tokens, or environment files are included.
- [ ] No copyrighted question-bank text is copied.
- [ ] Examples are synthetic, de-identified, or aggregate only.

## Review Quality

- [ ] JSONL examples pass `npm run validate`.
- [ ] New examples include a clear `failure_type`.
- [ ] New rule candidates avoid overfitting one lecture or subject.
- [ ] Metrics use aggregate values rather than private source names.
- [ ] README or docs are updated when workflow behavior changes.

## Release Notes

- [ ] State what changed.
- [ ] State what validation was run.
- [ ] State that private source material is not included.
- [ ] Link to the relevant issues or pull requests.

