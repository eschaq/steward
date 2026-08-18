---
name: Steward
colors:
  # These are the tokens :root actually defines in frontend/src/index.css.
  # Two surfaces, not one — see "Two modes" below.

  # --- light: every working screen (dashboard, item views, Message Center)
  surface: '#fff8f4'
  surface-lowest: '#ffffff'
  surface-low: '#fcf2ea'
  surface-mid: '#f6ece5'
  surface-high: '#f1e6df'
  surface-highest: '#ebe1da'
  on-surface: '#1f1b17'
  on-surface-variant: '#54433e'
  outline: '#71615c'          # darkened 2026-08-15 for AA — see Accessibility
  outline-variant: '#d9c1ba'  # decorative hairlines only, never a control edge
  field-border: '#988782'     # the edge of anything you type into or press
  hairline: 'rgba(135,115,109,0.18)'

  # --- ink: arrival moments only (sign-in, the estate hero)
  ink: '#211a14'
  ink-deep: '#17110c'
  on-ink: '#f9efe8'
  on-ink-muted: 'rgba(249,239,232,0.62)'
  on-ink-faint: 'rgba(249,239,232,0.42)'
  ink-hairline: 'rgba(249,239,232,0.16)'
  ink-accent: '#ffb59d'

  # --- clay (primary)
  primary: '#8e4831'
  primary-hover: '#74341e'
  primary-block: '#ac6046'
  on-primary: '#ffffff'
  clay-tint: '#ffdbd0'
  on-clay-tint: '#74341e'

  # --- sage (secondary)
  sage: '#d7e8c8'
  on-sage: '#2c3a24'
  on-sage-variant: '#3d4b34'
  sage-outline: '#bbccad'

  # --- archive (tertiary)
  archive: '#efe1cc'
  on-archive: '#4e4637'

  error-container: '#ffdad6'
  on-error-container: '#93000a'
typography:
  # Class names as implemented in index.css, not the Stitch scale.
  display:            # .display — estate hero, sign-in headline at >=900px tall
    fontFamily: Source Serif 4
    fontSize: 42px
    fontWeight: '600'
    lineHeight: 1.1
    letterSpacing: -0.02em
  signin-head:        # .signin__head
    fontFamily: Source Serif 4
    fontSize: 36px
    fontWeight: '600'
    lineHeight: 1.14
    letterSpacing: -0.015em
  headline:           # .headline
    fontFamily: Source Serif 4
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 1.2
  card-title:         # .card__title, .lockup__name at default size
    fontFamily: Source Serif 4
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 1.2
  ledger-number:      # .ledger__number
    fontFamily: Source Serif 4
    fontSize: 40px
    fontWeight: '600'
    lineHeight: 1
  body:               # body default
    fontFamily: Work Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 1.5
  body-sm:            # .card__notes, .signin__under
    fontFamily: Work Sans
    fontSize: 14.5px
    fontWeight: '400'
    lineHeight: 1.6
  field-label:        # .field > label — sentence case, never uppercase
    fontFamily: Work Sans
    fontSize: 13.5px
    fontWeight: '500'
  eyebrow:            # .eyebrow — uppercase section label
    fontFamily: Work Sans
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 1.4
    letterSpacing: 0.14em
  tag:                # .tag, .filter — uppercase archival mark
    fontFamily: Work Sans
    fontSize: 11px
    fontWeight: '600'
    letterSpacing: 0.06em
rounded:
  # Archival tag — chips only. Kept nearly square on purpose.
  tag: 3px
  image: 12px
  row: 14px
  block: 16px
  hero: 22px
  # Actions. Buttons are pills; chips never are.
  pill: 9999px
spacing:
  # index.css keeps one spacing variable; the rest are literals on the 8px grid.
  page-max: 1120px    # --page-max
  page-padding: 24px
  grid-gap: 16px
  card-padding: 16px 18px 18px
---

## Brand & Style

The design system is built upon the concept of "the steady hand." It facilitates difficult family transitions with a grounded, unhurried presence. The aesthetic rejects the frenetic energy of modern productivity tools in favor of a **warm, humanist minimalism** that feels more like a physical heirloom catalog than a digital database.

The visual direction avoids "gamification" entirely. There are no progress bars that demand completion or badges that reward speed. Instead, the UI uses generous whitespace and a tactile, paper-like quality to provide families with the emotional room to breathe and reflect. The style is "Plainspoken Luxury"—high-quality typography and subtle tonal shifts that communicate reliability and respect for the objects being managed.

### Revision — "Hearth & Archive" (2026-08-13)

The system was re-cut against the Claude Design redesign (`Steward Redesign.dc.html`). The palette, the type pairing, and every principle above are unchanged. What changed is the **register**: warm minimalism became warm *editorial*. Type is set larger and more confidently, a dark surface carries the moments that should feel like arriving somewhere, and counts appear as substantial tonal blocks rather than incidental text.

Three rules below were rewritten to match, and each is marked. Everything else held—most importantly the two that carry the brand: no shadows, and no gamification. The redesign states the same principle in its own words: the numbers "read as a ledger, not a score."

## Colors

The palette is rooted in natural, earthy pigments. **Warm Clay** (`#8e4831`) is
the primary action colour. **Soft Sage** (`#d7e8c8`) is the secondary. Both sit
on a **Warm Cream** ground (`#fff8f4`) rather than pure white.

### Two modes

The product runs two surfaces. This is not a light/dark toggle — nothing
switches, and which surface a screen uses is fixed by what that screen is *for*.

| | Ink | Cream |
| --- | --- | --- |
| Ground | `#211a14` (page behind: `#17110c`) | `#fff8f4` |
| Text | `#f9efe8`, muted `rgba(249,239,232,0.62)` | `#1f1b17`, muted `#54433e`|
| Hairline | `rgba(249,239,232,0.16)` | `rgba(135,115,109,0.18)` |
| Used by | sign-in; the estate hero on the dashboard | every working screen |
| Reads as | arriving at the house | the work you actually do there |

Ink is a **warm near-black**, not a neutral grey — that is what keeps the split
faithful to "warmth over sleekness" rather than a drift into dev-tool aesthetics.
It never carries dense reading, long lists, or a screen full of data. On sign-in
it is a photograph rather than a flat fill; on the dashboard hero the same
photograph is held far enough back to read as texture. See Photographic
Treatment.

Everything below the hero — filters, cards, ledger blocks, item views, the
Message Center — is Cream. A screen where someone is deciding something stays
light.

### Status colours

Desaturated on purpose, to lower the alert level. All six statuses the family
ever sees have a tone; a status an item can genuinely reach must never be
invisible. The data model has a seventh, `removed` — it is soft delete and is
never listed anywhere, so it has no tone and needs none.

| Status (data model) | Shown to the family | Fill / text | Reads as |
| --- | --- | --- | --- |
| `unclaimed` | Unspoken for | `#f1e6df` / `#71615c` | soft grey, receding until it's ready to be addressed |
| `claimed` | Spoken for | `#ffdbd0` / `#74341e` | a clay tint — one person has asked |
| `contested` | Needs a talk | `#efe1cc` / `#4e4637` | muted archive tan: a conversation, not an error |
| `resolved` | Settled | `#d7e8c8` / `#2c3a24` | the sage of settling; a quiet sigh of relief |
| `routed` | On its way | `#ebe1da` / `#54433e` | done and gone, receding again |
| `needs_clarification` | Needs a look | dashed `#71615c` outline, `#8e4831` text | still an open question — Steward has asked something |

A ledger block whose count is zero drops to the quiet neutral tone rather than
rendering a large numeral in a strong colour. An absence of things to attend to
should not look like an alarm.

### Accessibility — WCAG 2.1 AA

Every text-on-background pairing in this palette is computed, not eyeballed.
The full table lives in `frontend/README.md`; the two values that changed on
2026-08-15 are recorded here because this file is the source of truth for
colour.

**`outline` `#87736d` → `#71615c`.** It read as pleasantly quiet and measured
3.47–4.46:1 across the six light surfaces — under AA for body text on *every*
one of them, and it is used for eyebrows, secondary row text, and the
`unclaimed` chip. Darkened along the same hue until the worst backdrop
(`surface-highest`) clears 4.5:1. It now measures 4.80–5.89:1.

**`field-border` `#988782`, new.** Input and select borders used
`outline-variant` `#d9c1ba`, which measures 1.55:1 against the field fill —
WCAG 1.4.11 wants 3:1 for the boundary of a control, and at that ratio the
field had no visible edge for anyone with low contrast sensitivity.
`outline-variant` stays exactly as it is for decorative hairlines and dashed
edges; controls use the new token. It measures 3.11–3.43:1.

Nothing else moved. Ink, clay, sage and the status fills all passed as written
— the tonal restraint of this palette is in the *fills*, and the text on them
was already dark enough.

Decorative hairlines (`hairline`, `sage-outline` on a sage panel) sit at
1.2–1.3:1 and stay there. 1.4.11 governs the boundaries of components and
graphics needed to understand content; a divider between two paragraphs is
neither, and darkening them would cost the quiet layering the whole design
depends on.

## Typography

This design system utilizes a sophisticated pairing of **Source Serif 4** for headings and **Work Sans** for functional text. 

The Serif headings provide an authoritative yet warm voice, reminiscent of classic literature or personal correspondence. The Sans-Serif body text is chosen for its exceptional readability and "plainspoken" character; it is neutral and clear, ensuring that descriptions of family items remain the focus. 

Line heights are intentionally generous (1.5x - 1.6x) to prevent the text from feeling dense or overwhelming during emotionally heavy tasks.

## Copy

Plain language everywhere the UI speaks to a family member. The data model's
enum values (`unclaimed`, `contested`, `needs_clarification`) stay in the data
model and in the API; they are never rendered.

Implemented in `frontend/src/types.ts` as `STATUS_LABEL`, and used by every
surface that names a status — filter chips, card badges, and empty states alike.
`STATUS_MEANING` supplies the hover description on each.

| Enum | Label shown | Description on hover |
| --- | --- | --- |
| `unclaimed` | Unspoken for | Nobody has asked for this one yet. |
| `claimed` | Spoken for | One person has asked for this. |
| `contested` | Needs a talk | More than one person has asked for this. |
| `resolved` | Settled | The executor has settled who it goes to. |
| `routed` | On its way | On its way — donated, sold, or discarded. |
| `needs_clarification` | Needs a look | Steward couldn't place this one and has asked about it. |

The ledger blocks and hero marks use the same vocabulary in running text —
"8 unspoken for", "1 item contested", "Steward has asked".

Two consequences worth keeping:

- **Labels are nouns and phrases, not adjectives**, so they cannot be dropped
  into a sentence. The empty state quotes instead: *Nothing is marked "Needs a
  talk" right now.* Interpolating the label bare produces "Nothing is needs a
  talk right now."
- **`routed` has no entry in the branding doc's Voice list.** "On its way" is a
  build-time decision, present tense because Disposition starts at `pending` and
  nothing marks completion yet. Revisit when completion exists.

Failures are stated plainly and never swallowed — a backend that isn't running
says so by name, rather than rendering an empty grid that looks like an estate
with nothing in it.

## Layout & Spacing

The layout philosophy is based on a **Fixed, Centered Grid** for desktop to create a sense of focus and containment. Content should never feel like it is "escaping" to the edges of the screen.

- **Whitespace:** Use whitespace as a functional tool to separate different family branches or categories of items. Avoid packing information tightly.
- **Rhythm:** A strict 8px base unit governs all padding and margins. 
- **Adaptation:** the item grid is `auto-fill, minmax(300px, 1fr)`, so it collapses to one column on a phone without a breakpoint. Page padding stays 24px at every width; the sign-in body switches from bottom-aligned to centre-left at `min-aspect-ratio: 1/1`, which is the only layout breakpoint in the system.

## Elevation & Depth

To maintain the "kitchen table" feel, this design system avoids floating elements and harsh shadows. Depth is communicated through **Tonal Layering**:

1.  **Level 0 (Base):** the Warm Cream ground, `#fff8f4`.
2.  **Level 1 (Cards/Containers):** `#ffffff` for cards, `#fcf2ea`–`#ebe1da` for
    quieter fills. Card hover is a tonal shift to `#fcf2ea`, never a lift.
3.  **Outlines:** instead of shadows, "Ghost Borders" — 1px at
    `rgba(135,115,109,0.18)` on Cream, `rgba(249,239,232,0.16)` on Ink.

**There are no shadows in the implementation.** The one exception previously
carved out here (a diffused ambient occlusion for modals) has never been built,
because there are no modals. If one is ever added, that exception has to be
re-argued rather than assumed.

## Shapes

The shape language is **Soft and Organic**. While not fully rounded or "bubbly," every corner is softened to remove any sense of sharpness or clinical precision.

**Revised.** The scale is markedly rounder than the original 4px/8px. Containers now hold a generous curve, which is what lets a dark panel read as a printed plate rather than a modal:

- **Tag:** 3px — chips only. Nearly square, and the one place the system stays tight. See Chips below.
- **Image:** 12px — photographs of belongings, so they feel like physical prints laid on a table.
- **Row:** 14px — cards, inputs, notices.
- **Block:** 16px — the tonal ledger blocks.
- **Hero:** 22px — the dark plate and the estate hero.
- **Pill:** full — actions only.

The spread between 3px on a tag and full-round on a button is deliberate: it is what keeps a *label* and an *action* from ever being mistaken for one another.

## Components

### Buttons
**Revised.** Buttons are **pills** (full radius), not softened rectangles. They are substantial and unhurried in their padding: 54px for a primary action, 52px for the cream action on Ink, 44px for a sage secondary, 40px for the quiet ghost button in an app bar. Primary buttons use the **Warm Clay** fill with white text; on the dark surface the primary action inverts to a **Warm Cream** fill with Ink text. Secondary buttons use a simple Soft Sage outline. Hover states should be a subtle darkening of the color, never a flash or high-contrast change.

The pill is reserved for actions. Nothing that merely *labels* something is ever pill-shaped — see Chips.

### The Mark

A line-drawn gable: roof, wall, door, chimney, and a thread beneath. Terracotta
line on cream, or reversed out in cream on Ink. Stroke weight increases as the
mark shrinks so it holds together in an app bar; the chimney drops below 24px and
the thread below 28px, rather than degrading into smudges. Implemented as
`frontend/src/components/StewardMark.tsx`.

The mark and the sign-in photograph are both a symmetrical gable. That rhyme is
deliberate — keep it if either is ever re-cut.

### Photographic Treatment

Photography is **greyscale on disk** and takes its colour from a duotone layer:
a clay-to-ink gradient at ~0.86 opacity in `mix-blend-mode: color`. Shipping
greyscale is not an optimisation afterthought — it is the point. The source
photograph's own colour is discarded, which is what turns a picture of one
particular building into brand imagery.

Over it sit two scrims, and both earn their place:

- a **top band** (~18–22% of the frame) so the mark stays legible; skies blow out
  in the corner where the mark sits
- a **lower ramp** to near-black so form fields and body copy stay readable

On wide screens the lower ramp turns horizontal and the content column moves off
centre, so the subject sits *beside* the form rather than behind the headline.

**The same photograph carries into the estate hero after sign-in, held much
further back** — the ink layer sits near-opaque so it reads as texture behind a
working screen rather than as the subject. A hero as emphatic as the sign-in
would make the inventory feel like a landing page every time someone opened it.
An extra top band darkens the app-bar row, since that runs the full width and
the brightest part of the frame is on the right.

See docs/estate-agent-branding.md for what may and may not be photographed.

### Ledger Blocks
A block of tonal color carrying one count: an uppercase label, then a large Source Serif numeral with a plain-language unit beside it. Used for how an estate stands — settled, needing a conversation, awaiting a look.

They are a **ledger, not a score**. No bars, no targets, no percentage complete, no comparison between family members. A block whose count is zero drops to the quiet neutral tone.

### Cards
Cards are the primary vehicle for item management: `#ffffff` fill, 14px radius, 1px ghost border. The photograph sits inset with a 12px radius and a 10px margin, so it reads as a print laid on the card rather than bleeding to its edge. There is no "lift" on hover — the background shifts to `#fcf2ea` instead.

A card carries an archival status tag over the photo, then the era/brand as a tag, a Source Serif title, the condition notes, and a footer rule with the suggested disposition and the classifier's confidence.

**The title is the category, always.** The data model gives an item no name, so `ai_category` is the closest thing to one; `ai_est_era_or_brand` is provenance and belongs in a tag. Promoting the era to the heading reads fine for "Louis XV style" and badly for "signed, dated 1962" — a qualifier, not a thing.

### The estate switcher

The estate name in the hero is a button: it opens a small panel listing every
estate the account belongs to, marking the current one in the ink accent, with
"Start another estate" beneath a hairline. It is on all four signed-in screens,
because which estate you are in is the context every screen is drawn in rather
than a setting kept somewhere.

**This is the first floating element in the system**, and the no-shadow rule
holds anyway: the panel separates from the hero by going a shade *darker* than
it — `ink-deep` on `ink` — with a 1px `ink-hairline` edge. Tonal layering, the
same as everywhere else. If a second floating element is ever added, it inherits
this treatment; a shadow still has to be re-argued rather than assumed.

It is `position: fixed`, not absolute. `.hero` is `overflow: hidden` so it can
clip the gable photograph to its 22px radius, and an absolutely-positioned panel
would be cut off at the hero's edge. Fixed escapes that clip, and the hero sets
no transform or filter, so it does not become a containing block. Anything else
placed inside the hero that needs to overflow it has the same problem.

### Subtabs

One screen, three addressable sections. Used on Review, where the working table
and the two reflective panels — how things have landed, what Steward has
learned — were stacked on a single scroll, putting slow reading in front of a
quick task every visit.

They borrow the app bar's treatment rather than inventing one: **Source Serif
17px, a 2px rule under where you are**, sitting on the hairline that divides the
strip from the panel below. Clay (`#8e4831`) rather than the ink accent, which
has nothing to lift off on cream. Never a filled chip and never a pill — chips
are archival tags on objects and pills are actions, and a section marker is
neither.

At 560px the strip becomes full-width stacked rows, since two of the three
labels are a phrase rather than a word and three ragged wraps read as noise.

Each tab is a real URL (`/review/inventory`, `/review/landed`,
`/review/learned`), so a section is something a family can send each other, and
the bare path resolves to the first tab.

### Chips & Status Indicators
Status chips use the muted palette defined in the Colors section. They are rectangular with a 3px radius, **never pill-shaped**, to maintain an "archival tag" aesthetic — a label tied to an object, the way a museum tags a piece. Set them in uppercase Work Sans at 11px with generous letterspacing, so they read as a catalogue mark rather than a button.

This rule survived the revision unchanged, and it is load-bearing: with actions now fully round, chip shape is what distinguishes a thing you can press from a thing that is merely true.

### The hero clip

The sign-in screen's gable is an eight-second video, generated with **Veo 3.1
Fast** on Vertex AI and seeded with `hero-gable-landscape.jpg` as its first
frame — so it is the established photograph moving, not a second building that
resembles it. Almost nothing happens: the light shifts across the brickwork as
if a cloud is passing a long way off. Locked-off camera, no pan, no push-in.

`filter: grayscale(1)` on the video element is load-bearing, not decoration.
Veo warms the clip from monochrome into natural colour across its eight seconds
(measured red/blue spread: 0 → 24 → 14), which would fight the terracotta
duotone and flash at the loop point. Desaturating removes that and leaves a 2.9%
luminance difference between last frame and first, which reads as the light
moving rather than a seam. The duotone and scrim layers then colour the video
exactly as they colour the still.

The clip also carries a **4% scale drift over 48 seconds**, alternating. Veo's
own movement is too small to survive the duotone and scrim — it plays, and still
reads as a photograph. The drift is deliberately much slower than the eight-
second loop so the two never beat against each other.

**Sign-in only.** The `.hero` app bar carries the same gable on every signed-in
screen, and it stays a still there: a loop running behind the review table while
someone works through forty items is the opposite of unhurried, and it would
burn battery on the screens people actually sit on. Ink is for arrival moments;
so is motion.

The still remains the element's `background-image` and the video's `poster`, so
a blocked autoplay, a decode failure or `prefers-reduced-motion: reduce` all
land on the same picture with no layout change.

### Breakpoints

Two, both measured rather than picked:

- **820px** — the review table stops being a table (columns collapse to zero
  width, rows triple in height) and becomes one card per item, each cell
  carrying its own column heading. The item placard drops to a single column at
  the same width.
- **560px** — the app bar tightens its gaps and drops to 16px links. It wraps
  at any width; `.hero` is `overflow: hidden`, so a nav that overflows
  disappears rather than scrolling.

Nothing else needs a breakpoint: the dashboard, Message Center and Family
screens are card and single-column layouts that reflow on their own.

### Status marks

Each of the six statuses carries a small drawn mark inside its chip, so the set
is separable without hue (WCAG 1.4.1). One stroke weight (1.4px), all on a 12px
square, no fills except the one that means something, no corner flourishes — a
pencil mark in a ledger margin, matching the archival tag it sits in. Never a
warning triangle; nothing here is an alarm.

| Status | Mark | Why that shape |
| --- | --- | --- |
| `unclaimed` | open ring | nobody's mark on it yet |
| `claimed` | filled ring | one name on it |
| `contested` | two overlapping rings | two people, not a collision |
| `resolved` | tick | the way you'd tick a line on a list |
| `routed` | arrow | it has left |
| `needs_clarification` | question mark | asked quietly |

The marks are `aria-hidden`: the chip's label already says the word, and a
screen reader should not hear it twice. They are for the eye scanning a grid of
thirty-eight cards, where six desaturated warm fills read as one wash to anyone
with a red-green deficiency.

### Input Fields
Inputs are simple and unobtrusive. Use a Warm Cream fill slightly darker than the background, with a 1px border — **including on the Ink surface and over photography**. A translucent dark field dissolves into whatever sits behind it and stops looking like somewhere you can type; the cream keeps it an object on the surface. Where cream fields stack above a primary button, that button must be Warm Clay, or it reads as one more field rather than the thing you press. Labels always sit above the field in **Work Sans Medium**.

**Labels are sentence case.** Never the uppercase letterspaced treatment used for eyebrows and tags: a field label is an instruction to a person, a tag is a mark on an object. Uppercase labels were most of what made an early sign-in screen read as enterprise software rather than something a family would use.

### Lists — not yet built
Lists of family members or item categories should have generous vertical padding (20px+) so each row feels distinct and respected. No list surface exists yet; this is a rule for when the Family and Message Center screens land.

### The "Heirloom" Component — not yet built
The item *detail* view: a centred photo, a Source Serif 4 title, and a wide-margined description below, mimicking a museum placard. `ItemCard` is the grid tile, not this — it is left-aligned and denser by design. The detail screen has not been built.