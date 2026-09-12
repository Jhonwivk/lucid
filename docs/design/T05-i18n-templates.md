# T05 — bilingual chrome and built-in templates

Internal note after reading `lucid/.cursor/skills/frontend-design/SKILL.md` and preserving the T04 Collation Desk direction.

## What this slice adds

Product chrome is `en` / `zh-CN`. Project titles, summaries, filenames, rule statements, and other persisted records are not auto-translated.

Six fictional mixed-material fixtures are listed on My Analyses as a ledger, not a card grid. Using a template POSTs `/api/templates/{id}/instantiate` and opens the new project's Materials workspace.

## Visual continuity with T04

- Same mineral paper, steel mark, Instrument Serif + Atkinson Hyperlegible.
- Template catalog is a ledger of named cases under the analysis list, with category, source-type marks, and a single Use template action.
- Template fixture stamp uses the steel family; demo data keeps the cobalt stamp. They are not success badges.
- No numbered markers on the unordered template list. Workspace nav remains sequential.

## Honesty

Built-in template seeding reads real fixture bytes for size/checksum and writes authored understanding/rules/scenario/SolveRun metadata from `template.json`. It is not TXT/PDF/CSV/XLSX/image import, OCR, or LLM extraction. SolveRun rows remain `claimed_execution=false` / `execution=not_executed`.
