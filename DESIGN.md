# LUCID visual design

Status: current workbench direction. The UI is a quiet, evidence-first single-user workspace rather than a marketing page or an Agent control console.

## Product surfaces

1. **Materials** — evidence, source spans and import status.
2. **Modeling** — one Agent draft, review actions and provenance.
3. **Baseline** — confirmed baseline, scenario revisions and formal inputs.
4. **Results** — deterministic candidates, explanations, what-if and export.

## Visual system

- Canvas: white `#ffffff`; panels: warm grey `#f6f5f4`.
- Ink: warm charcoal `#37352f`; deep ink `#1a1a1a` for headings/actions.
- Hairline: `#e5e3df`; link/focus: `#0075de`.
- Unknown/incomplete: `#dd5b00`; conflict/error: `#e03131`.
- Buttons use an 8px radius; panels use a 12px radius.
- Use system fonts with Chinese fallbacks; do not download proprietary fonts.
- Keep UUIDs, checksums and raw API details inside expandable technical sections.

## Interaction rules

- Show the current evidence, claim, formal input and result in the same lineage.
- Make unknown, blocked, invalid and infeasible states visible.
- Never show a fake schedule, fake Agent draft or fake provider success.
- What-if actions create a new revision; they do not mutate the confirmed baseline.
- Results show ranked candidates, explanation and source references.
- Respect keyboard focus and `prefers-reduced-motion`.

The old M2 collation-desk note is historical. This file is the current visual source of truth.
