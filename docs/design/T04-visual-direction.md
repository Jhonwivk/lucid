# T04 visual direction — LUCID collation desk

> Historical M2 brief. Stage 1 UI follows [`DESIGN.md`](../../DESIGN.md) (Notion-inspired workbench; the VoltAgent Notion DESIGN.md file was selected and **not fetched**). Keep this file as the T04 record.

Internal design brief. Written after reading the official Anthropic `frontend-design` skill in full, and before UI implementation.

Process used: ground in subject matter → compact token system → uniqueness review against AI-default clusters → then code.

## Purpose and primary user

LUCID is a single-user business-constraint and solution-planning workbench. The primary user is a planner working alone from existing documents and tables. They are not here to chat, administer an organization, or watch a developer dashboard. They are here to turn messy evidence into a reviewable formal model, compare constrained plans, and keep working when conditions change.

The product’s characteristic object is **versioned uncertainty sitting next to a confirmed decision** — not a KPI, not a chat transcript.

## Single job of each major page

| Surface | Route | One job |
| --- | --- | --- |
| My Analyses | `/analyses` | Choose which analysis to continue, or start a new one from real records. |
| Materials | `/analyses/:projectId/materials` | Inspect source-evidence metadata that will ground the model. |
| Understanding | `/analyses/:projectId/understanding` | Inspect the latest interpretation and its lineage, with unknowns/conflicts held open. |
| Scenarios | `/analyses/:projectId/scenarios` | Inspect formalization lineage and tell a confirmed baseline from a hypothetical. |
| Results | `/analyses/:projectId/results` | Inspect SolveRun persistence records without pretending a solver ran. |

The four workspaces are one continuous analytical environment for a named project, not four demo pages.

## One concrete aesthetic direction

**Collation desk** — a precision editorial / decision studio modeled on comparing manuscript versions on a cool mineral writing surface.

Not a SaaS admin console. Not a marketing landing. Not a newspaper broadsheet. The room this UI belongs in is a planner’s desk: paper, a steel ruling pen, annotated drafts, and a clear difference between a finished inscription and an unfinished note.

The first thing on My Analyses is the **ledger of real analyses**, not a hero headline.

## Typography direction

Two families, clearly distinct:

- **Instrument Serif** — analysis titles and workspace names. The type treatment itself carries the product: a named analysis is the object of work, so its title is display, not a muted label.
- **Atkinson Hyperlegible** — UI, body, metadata. Chosen because this product’s job is to keep unknowns visible; a face designed for distinguishability is the vernacular, not a fashion serif/sans pair.

Scale (Bringhurst-ish, modest):

- Display analysis title: ~2.25–2.75rem, serif, tight leading
- Workspace title: ~1.75rem
- Body: 1rem / 1.55
- Meta: 0.8125rem, sentence case, no tracked-out caps

Line length for prose stays under ~68ch. Serif titles may run longer. No single-word color/italic accent inside headlines. No ALL-CAPS eyebrows. No `Word — fragment` em-dash labels.

## Palette direction

Core tokens (named hex):

| Token | Hex | Role |
| --- | --- | --- |
| Paper | `#E6EAE7` | Page ground — cool mineral, not cream `#F4F1EA` |
| Surface | `#F3F5F2` | Raised writing surface |
| Ink | `#1E2C32` | Primary text — slate, not tinted near-black `#0B0B0B` |
| Margin | `#5B6A6F` | Secondary text |
| Steel | `#2F5E73` | Interactive mark / focus / confirmed rail |
| Unknown | `#8A6418` | Unresolved facts (text); hatch uses a lighter wash of the same family |
| Conflict | `#8F2F2C` | Conflicted / rejected evidence |
| Demo | `#3D5A8A` | Ink-stamp for `is_demo` records only |

Confirmed decisions sit on clean paper with a solid steel or ink edge. Unknown / missing / conflicted facts sit on a **hatched field**. Demo records use a cobalt stamp, never a success-green badge.

## Spatial / composition strategy

Left-aligned throughout. No centered marketing stack.

My Analyses:

```
[LUCID] My analyses                                    API ready
----------------------------------------------------------------
My analyses                         |  Start analysis
Choose a record to continue.        |  Title
                                    |  Summary
[Find]          All  Mine  Demo     |  [Create analysis]
----------------------------------------------------------------
Title                 Maturity   Latest real cue        Updated
[stamp] Demo title    open       Understanding v2       11 Sep
User title            materials  No understanding yet   11 Sep
```

- The list is a **ledger** (rows with a hair-thin rule), not a grid of identical rounded cards.
- The create form sits in an asymmetric right column on desktop and stacks above the ledger on a narrow window.
- One radius is not applied to everything: ledger rows are nearly square (2px); the composer is the only softer panel.

Workbench:

```
[LUCID] My analyses / {title}                          API ready
{title}   demo stamp?
updated · workflow maturity from API
Materials — Understanding — Scenarios — Results   (real sequence)
----------------------------------------------------------------
Workspace stage (wider)            | State of record
                                   | latest pointers
                                   | lineage counts
```

Numbered/sequential workspace navigation is justified: Evidence → Understanding → Scenario → Results is an actual sequence. Sequence markers are not used on unordered content (rules, materials).

On a narrow window the record strip moves under the header; workspace nav becomes a horizontal row; the composer stacks.

## Motion strategy

Motion answers navigation and confirmation only:

- Workspace/stage swap: short opacity crossfade (~160ms), no translate, no stagger.
- Opening the create form: the composer appears in place.
- No perpetual ambient motion, no per-card hover lifts, no loading spinners as personality.
- `prefers-reduced-motion: reduce` removes the stage fade.

Focus-visible uses a steel outline. Hover on ledger rows inks the title, not a drop shadow.

## The one justified aesthetic risk

**Hatch as a material for uncertainty.** Unknown, missing, and conflicted facts are drawn on a diagonal stipple field with a warm or conflict-colored edge. Confirmed / accepted / present facts sit on clean paper with a solid edge.

Why this is the one bold move: the product fails if uncertainty looks like a badge variant of success. Hatch is how unfinished drawing is already understood, so it encodes the rule “do not treat this as decided” without a dashboard legend.

Risk: hatch can look like a rendering bug or visual noise. Mitigation: use it only on fact rows (unknowns, conflicts, null quantities, unexecuted SolveRun labels), never as page wallpaper; keep the rest of the UI quiet.

## Patterns intentionally avoided (generic / AI-templated)

Rejected after skill calibration, including first impulses that would have been “any workbench”:

1. Warm cream `#F4F1EA` + terracotta `#D97757` + high-contrast serif (Claude-interaction tell).
2. Near-black ground + acid green / vermilion.
3. Broadsheet: zero radius, dense newspaper columns, hairline grid as the whole identity.
4. SaaS-card kit: identical large radii, soft grey shadows, gradient washes, KPI tiles.
5. Template chrome: tracked ALL-CAPS eyebrows, middle-dot meta strings, `WORD — fragment` labels, `#0B0B0B` standing in for black, monospace as decorative data labels, `→` on every button.
6. Purple/blue gradient hero, giant centered headline + three feature cards, glassmorphism, Inter/system-default UI, fake charts, Newsreader+Figtree+teal rounded glass (the M0 shell look — a decoration pass, not a new identity).

## Uniqueness review (skill pass 2)

A generic “serious planning app” prompt would likely have produced cream paper, a terracotta accent, Inter or Newsreader, and a card grid of projects with circular status pills. This brief changes all four: mineral paper, steel mark, Atkinson + Instrument Serif, ledger + hatch. If those four are executed, the UI should not be mistaken for a dashboard template.

## Honesty constraints (binding on visual language)

- Demo vs user-created is a stamp, not a “sample success.”
- `claimed_execution=false` / `execution=not_executed` is never styled as an optimization result.
- Null cost / capacity / permission render as unknown, never as `0` / `false`.
- Upload, AI extraction, and solver actions that are not implemented stay disabled or labeled as coming later — no fake completion states.
