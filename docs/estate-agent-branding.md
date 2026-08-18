# Branding & Visual Persona — Estate Belongings Disposition Agent

Last updated: 2026-08-13
Per SOP Phase 2.4 — defined before build starts.

---

## Product Name

**Steward**

Naming history: "Kinfolk" was the original working name but was dropped — it read as trying to be charming about something that isn't charming, and collides with an existing lifestyle magazine brand. "Gather," "Held," and "The Sorting Table" were also considered. "Steward" won because it's accurate to the executor's actual role (legal and emotional responsibility, not liquidation), and reframes the product's whole story around fulfilling a responsibility to family rather than sorting/selling — a better register for a grief-adjacent product and a stronger narrative for judges.

## Tagline

**"Decide together. Steward it well."**

Revised from the original ("Decide together. Sort it out. Move forward.") to match the name — "steward it well" carries the responsibility framing through instead of ending on a logistics note.

## Visual Persona

One sentence: **"A quiet, steady hand at a kitchen table — warm, unhurried, plainspoken. Not clinical, not cutesy."**

Evolved during build (Aug 13): the sign-in/hero moments use a warm-toned dark treatment (terracotta duotone over architectural photography — rooflines, timber, stone) rather than pure light mode, while the working surfaces (dashboard, item views, Message Center) stay in the original warm cream register. The dark hero reads as "arriving at the house," the light interior reads as "the work you actually do there" — a considered split, not a drift from the original intent. This is a grief-adjacent product; it must never feel like a reseller-hustle app or a legal-tech product regardless of which mode a given screen uses.

The tone is closer to a well-designed family-recipe box than a SaaS dashboard.

## Color Palette

- **Primary:** Warm clay / terracotta (#B5674D) — grounded, human, avoids both corporate blue and funeral black
- **Secondary:** Soft sage (#8A9A7E) — calm, growth-adjacent without being twee
- **Accent:** Warm cream (#F2E9DC) — background/space for working surfaces
- **Hero/dark treatment:** warm espresso-brown ground with terracotta gradient accents, used only for sign-in and other arrival moments, not for interior working screens
- **Status colors (functional, not thematic):** muted amber for Contested, muted green for Resolved, soft gray for Unclaimed — deliberately desaturated so the dashboard doesn't feel alarm-driven

## Typography

One family: a humanist serif for headings (e.g., Lora or similar — warmth, readability, not corporate) paired with a clean sans for body/UI (system-ui stack is fine — this isn't the place to spend build time on custom type).

## Logo Concept

Brief for Ideogram: a simple line-drawn house or open box silhouette, warm terracotta line on cream, with a small human touch — two overlapping hands, or a subtle thread connecting shapes — suggesting care and responsibility without being literal or twee. Avoid: moving-box icons (too logistics-focused), gavel/scale icons (too legal), price-tag icons (too reseller-focused).

## Music Direction

Persona: warm, unhurried, plainspoken → **warm acoustic, light piano, unhurried tempo** (matches the "friendly small business assistant" mood category from the SOP's persona table, pulled toward slower/gentler than a typical small-biz assistant given the grief adjacency).

## VO Voice Direction

Calm, warm, mid-register — not corporate-narrator, not upbeat-tech-demo energy. Should sound like someone explaining something patiently to a tired family member, not pitching a product.

## Voice — status & UI copy

Plain, human language over clinical enum values wherever the UI surfaces status to a family member:
- unclaimed → "unspoken for"
- claimed → "spoken for"
- contested → "needs a talk"
- resolved → "settled"
- needs_clarification → "needs a look"

## What This Rules Out

- No countdown timers, urgency badges, or gamification anywhere in the UI
- No stock "family holding hands" imagery, and no stock corporate/SaaS photography (dashboards, data overlays, inventory-management imagery) — hero photography should be genuinely domestic and specific (architecture, materials, quiet interior detail), not generic stock
- Dark treatment is reserved for arrival/hero moments only — the screens where people do the actual work of deciding stay in the warm, light register
- **No domestic interior standing in for a family's own home.** A photographed living room reads as a claim about *their* house, and it isn't one. Architectural detail is the exception — see below.
- No shadows anywhere. Depth is tonal layering and 1px hairlines

## Revision — "Hearth & Archive" (2026-08-13)

Re-cut against the Claude Design redesign (`Steward Redesign.dc.html`). The name, tagline, persona, palette, and type pairing are unchanged. The register moved from warm minimalism to **warm editorial**: larger, more confident type; a dark surface for the moments that should feel like arriving somewhere; counts as substantial tonal blocks.

**The dark surface.** Ink (#211a14) with cream type now carries the sign-in plate and the estate hero. This is *not* a dark mode — the product does not have one, nothing toggles, and Ink never holds dense reading or a screen full of data. It is the cover of the catalogue, not its pages. Ink is a warm near-black, not a neutral gray; the original rule's intent (warmth over sleekness) is intact, which is why the rule was revised rather than dropped.

**Shape.** Containers are rounder (12–22px) and actions are pills. Status chips stay nearly square at 3px — "archival tag, never pill" survives, and now does more work than before: with actions fully round, chip shape is what separates a thing you can press from a thing that is merely true.

**Counts, not scores.** Where the interface shows how an estate stands, it does so as a ledger — a label and a number. No bars, no targets, no percentage complete, no comparison between family members. A count of zero goes quiet rather than rendering a large numeral in a strong colour; an absence of things to attend to should never look like an alarm. This is the anti-gamification rule holding under new visual pressure, not an exception to it.

**Status colour.** Contested is the archive tan `#efe1cc` — the palette's muted amber, in the redesign's own "needs a conversation" tone. All six item statuses now carry a tone — see `docs/design/steward/DESIGN.md`.

## Brand imagery — architectural detail (2026-08-13)

Revised after building the sign-in screen. The rule against stock interiors was
drawn too wide: it also ruled out the one kind of photography that genuinely
suits this product.

**Permitted:** tight architectural detail — a gable, a roofline, eaves, a
doorway — treated as brand imagery. It must be
1. **cropped close enough to be a shape, not a house.** No establishing shots. If
   you can tell whose home it is, it is the wrong crop.
2. **run through the clay-to-ink duotone.** The source ships greyscale; colour
   comes from the treatment. This is what does the abstracting — the same photo
   untreated would read as a stock house.
3. **quiet in the lower half**, since a scrim and a form sit over it.

**Still ruled out:** interiors, rooms, furniture in situ, anything with people,
and any photograph presented as though it were the family's own.

The distinction is between imagery that says *"this is the kind of thing Steward
is for"* and imagery that pretends to say *"this is yours."* The first is brand
work. The second is a lie the product cannot back up, since before someone signs
in we do not even know which estate they belong to.
