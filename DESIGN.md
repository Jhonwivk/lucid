# LUCID visual design — Stage 1 workbench

Status: binding for Stage 1 UI.  
Fetched: 2026-09-12.

## Selected reference (fetched)

VoltAgent/awesome-design-md, Notion analysis:

- https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/notion/DESIGN.md
- Raw: https://raw.githubusercontent.com/VoltAgent/awesome-design-md/main/design-md/notion/DESIGN.md
- License: MIT, Copyright (c) 2026 VoltAgent  
  https://github.com/VoltAgent/awesome-design-md/blob/main/LICENSE

This file was fetched on 2026-09-12 (source page `version: alpha`, `name: Notion-design-analysis`). It is an **adaptation** for LUCID’s single-user modeling workbench. It is **not** a copy of Notion’s marketing homepage, logos, proprietary Notion Sans, purple “Get Notion free” CTA, navy hero band, sticky-note illustrations, pastel feature tiles, or pricing tables.

The earlier M2 “collation desk” note in `docs/design/T04-visual-direction.md` remains historical. Stage 1 UI follows this document.

## What was adapted (product workbench, not marketing)

From the reference’s **product/workspace** language:

- Canvas white and warm charcoal ink (`#37352f`)
- Soft surface (`#f6f5f4`) and hairline borders (`#e5e3df`)
- Rectangular buttons at 8px radius (not universal pills)
- Cards/panels at 12px radius
- Body leading 1.55; 600-weight headings with slight negative tracking
- Segmented underline tabs for workspace navigation
- Link blue (`#0075de`) for inline links only
- Semantic warning/error (`#dd5b00` / `#e03131`) for unknown and conflict

Primary actions use **ink-deep black rectangles**, which matches a dense editor, not Notion’s signature marketing purple.

System fonts with Chinese fallbacks. No Google Fonts. No proprietary webfont downloads.

```
ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
"PingFang SC", "Hiragino Sans GB", "Noto Sans SC", "Microsoft YaHei", sans-serif
```

## Product identity

LUCID stays LUCID: a single-user business-modeling workbench. The first screen is **My analyses**, not a landing hero. Work happens in four connected workspaces:

1. Materials — peer evidence (question text, pasted text, files)
2. Modeling — one Business Modeling Agent draft + human review
3. Baseline — immutable pre-solver handoff
4. Results — solver not implemented; no fabricated schedules

Deep links `/understanding` and `/scenarios` redirect to Modeling and Baseline.

## Token system (implemented)

| Token | Value | Role |
| --- | --- | --- |
| `--paper` | `#ffffff` | Page canvas |
| `--surface` | `#f6f5f4` | Soft panels |
| `--ink` | `#37352f` | Body (warm charcoal) |
| `--ink-deep` | `#1a1a1a` | Headings and primary buttons |
| `--margin` | `#5d5b54` | Secondary text |
| `--line` | `#e5e3df` | Hairline |
| `--steel` | `#0075de` | Links / focus, not the primary CTA |
| `--unknown` | `#dd5b00` | Incomplete / unknown |
| `--conflict` | `#e03131` | Rejected / conflict |

Geometry: 8px buttons, 12px panels. UUID, checksum, and API paths stay in `<details>`.

## Layout

```
Analyses
[ title + search ]     [ question / paste / files composer ]
[ six templates ]
[ ledger of real projects ]

Workbench
[ crumb + title + question ]
[ Materials | Modeling | Baseline | Results ]
[ connected workspace ]
```

Modeling on wide screens is a three-pane workbench (sources / claims / activity). On narrow screens those panes become tabs. Keyboard focus uses a 2px link-blue outline. `prefers-reduced-motion` disables ornamental animation.

## Honesty in copy

- Missing `LUCID_MODEL_*` is a configuration blocker, not a successful draft.
- Missing Azure Content Understanding leaves complex files incomplete.
- Results states solver not implemented.
- Unknowns stay unknown; they are not coerced to zero.
