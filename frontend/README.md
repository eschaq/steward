# Steward — frontend

React + Vite + TypeScript, with react-router-dom. Three screens: sign-in, the
inventory dashboard, and the item detail view. Both are wired to the real backend and real Firebase Auth — there is
no mock data anywhere in here.

| Path                          | Purpose                                            |
| ----------------------------- | -------------------------------------------------- |
| `src/firebase.ts`             | Firebase client SDK; `API_BASE_URL`, `ESTATE_ID`    |
| `src/auth.tsx`                | `AuthProvider` / `useAuth`; plain-language errors    |
| `src/api.ts`                  | Backend calls with the ID token attached            |
| `src/types.ts`                | Item shape, and all six statuses with their meanings |
| `src/index.css`               | The design system as CSS custom properties          |
| `src/screens/SignIn.tsx`      | Email/password sign-in                              |
| `src/screens/Dashboard.tsx`   | Inventory grid, status filters                      |
| `src/screens/ItemDetail.tsx`  | One item: placard, facts, claim action, thread      |
| `src/components/`             | `ItemCard`, `StatusChip`, `StatusFilters`, `StewardMark`, `Claimants`, `MessageThread` |
| `public/brand/`               | Hero photography (greyscale; duotoned in CSS)       |
| `mockups/`                    | Design comps — not built, not served                |
| `verify.mjs`                  | Drives the real app in a real browser (Playwright)  |

## Running it

Both servers, in two terminals:

```bash
cd backend  && .venv/bin/uvicorn api:app --port 8000
cd frontend && npm install && npm run dev        # http://localhost:5173
```

Copy `.env.example` to `.env.local` and fill it in —
`firebase apps:sdkconfig WEB --project steward-hackathon-505217` prints the
values. `.env.local` is gitignored; `.env.example` is not.

Sign in with a seeded test user, e.g. `steward-test-executor@example.com`
(password set by `backend/dev_tokens.py`).

Nothing is deployed. Cloud Run is separate, later work.

## How it hangs together

- **The frontend never touches Firestore.** It uses Firebase Auth to get an ID
  token, and everything else goes through the backend API. That's the trust
  boundary the two-service split exists to hold (CLAUDE.md), and it's why
  `firebase.ts` exports `auth` but no Firestore handle.
- **Tokens are fetched per request**, not cached in app state. `getIdToken()`
  returns the current token and refreshes it near expiry, so a session open
  longer than an hour keeps working.
- **Failures are stated, not swallowed.** A backend that isn't running says so,
  by name and with the command to start it, rather than rendering an empty grid
  that looks like an estate with nothing in it.

## All six statuses, deliberately

The Stitch mockup's filter row had three tabs — unclaimed, claimed, contested.
The data model has **six**. `resolved`, `routed`, and `needs_clarification` are
states an item genuinely reaches, and the seeded estate currently holds ten
resolved items and three waiting on a clarifying question. A tab with a zero
count is honest; a missing tab hides a state from the family entirely.

Counts sit on every tab, and an empty one stays visible at reduced opacity
rather than disappearing.

## Design — "Hearth & Archive"

Rebuilt to match the Claude Design redesign (`Steward Redesign.dc.html`, project
`cbc54990`). Same palette and type pairing as `docs/design/steward/DESIGN.md`
(Source Serif 4 + Work Sans, clay / sage / cream); different shape:

- a **dark editorial surface** (`#211a14`) carrying the sign-in and the
  dashboard hero, with type set large over it
- **tonal ledger blocks** — big Source Serif numerals on sage / clay / archive
  fills. A ledger, not a score: no bars, no targets, no "percent complete"
- **archival tag chips** — 3px radius, uppercase, letterspaced. A tag tied to an
  object, not a pill
- **generous container radii** (12–22px) and **pill-shaped actions**
- still no shadows anywhere; depth is tonal layering and 1px hairlines

### Three deliberate divergences from DESIGN.md

The redesign contradicts the written design system in three places. The code
follows the redesign; **DESIGN.md has not been changed** — that edit is pending
approval.

| Topic       | DESIGN.md says                            | Redesign does                    |
| ----------- | ----------------------------------------- | -------------------------------- |
| Dark themes | "No dark-mode-first design"               | dark `#211a14` hero and sign-in  |
| Radius      | 4px controls, 8px cards                   | 12–22px containers               |
| Buttons     | "Soft" 4px corner radius                  | pill (999px)                     |

They agree on everything else, including the two that matter most to the brand:
no shadows, and no gamification — the redesign's own note says the numbers
"read as a ledger, not a score."

### Status colours

Four of six now come from the redesign directly rather than being invented:

| Status                | Colour                          | Source                                  |
| --------------------- | ------------------------------- | --------------------------------------- |
| `unclaimed`           | `#f1e6df` / `#87736d`           | palette — recedes, per DESIGN.md        |
| `claimed`             | `#ffdbd0` / `#74341e`           | redesign — the claim cards in 1d        |
| `contested`           | `#efe1cc` / `#4e4637`           | redesign — its "needs a conversation"   |
| `resolved`            | `#d7e8c8` / `#2c3a24`           | redesign — its "settled" sage           |
| `routed`              | `#ebe1da` / `#54433e`           | **derived** — quiet, done and gone      |
| `needs_clarification` | dashed outline, clay text       | **derived** — echoes 1c's dashed "You"  |

### The sign-in hero

A full-bleed photograph of a gable, generated with Ideogram, with the form
sitting on it. Portrait and landscape crops of the same subject are swapped by
`@media (min-aspect-ratio: 1/1)`.

The photographs are **greyscale JPEGs**, and that is deliberate rather than an
optimisation afterthought: the duotone layer discards the source colour anyway,
so shipping greyscale costs nothing visually, saves a CSS filter at runtime, and
made a 6 MB PNG into a 308 KB JPEG. Full-resolution originals live in
`brand-source/` (gitignored) if they need re-exporting.

| File                                    | Size   | Used at            |
| --------------------------------------- | ------ | ------------------ |
| `public/brand/hero-gable-portrait.jpg`  | 308 KB | aspect ratio < 1:1 |
| `public/brand/hero-gable-landscape.jpg` | 286 KB | aspect ratio ≥ 1:1 |

Two scrims sit over the photo. The top band exists because both crops have blown
sky exactly where the mark goes; the lower ramp carries the frame to near-black
so the form is readable. On wide screens the ramp turns horizontal and the
content column moves off centre — the landscape gable is near-symmetrical, and a
centred column would sit directly on its apex.

Cream fields sit on the photograph rather than translucent dark ones — a dark
field dissolves into the image and stops reading as somewhere you can type. That
in turn forces the primary button to clay: with cream fields above it, a cream
button looks like a third field.

The estate hero on the dashboard carries the same landscape crop, but with the
ink layer near-opaque so it reads as texture rather than subject.

### The mark

`src/components/StewardMark.tsx` — the gable line drawing from the logo brief,
with `StewardLockup` pairing it with the wordmark. Stroke weight increases as it
shrinks; the chimney drops below 24px and the thread below 28px rather than
turning to mush. Used on sign-in and in the dashboard app bar.

### What was not carried over

- **The mockups' photography.** The `lh3.googleusercontent.com` images in the
  redesign are Stitch placeholders.
- **The iOS frame.** `ios-frame.jsx` is a canvas presentation scaffold
  (`@ds-adherence-ignore`, "omelette starter"), not app material. `support.js` is
  the generated design-canvas runtime. Neither has anything to port.
- **The other three screens.** The redesign shows Home, Item detail, Family, and
  Resolution. This app has sign-in and the dashboard, so the language was applied
  to those rather than four new screens being built thinly.
- **"Forgot password?"** It was in the approved mockup, but there is no reset
  flow in the backend and a link that goes nowhere is worse than its absence.
  Add the link when the flow exists.

## Verifying it actually works

`verify.mjs` drives a real Chromium: signs in as the seeded executor, waits for
the dashboard, reports what rendered, clicks a filter, and screenshots both.

```bash
node verify.mjs                                  # defaults to the executor
node verify.mjs someone@example.com their-pw
```

Last run against real Firestore:

```
signed in as : steward-test-executor@example.com
blurb        : 24 belongings in this estate. Take your time.
filters      : Everything 24 | Unclaimed 8 | Claimed 2 | Contested 1 |
               Resolved 10 | Routed 0 | Needs a look 3
cards        : 24
badges       : resolved 10, unclaimed 8, needs_clarification 3, claimed 2, contested 1
Contested filter -> 1 card, all Contested
```

Most of those 24 items are fixtures the backend test suites left behind
(`test-override-hist-*`, `test-ep-*`, and so on). They are real Firestore
documents, not seeded UI data — but they are why the inventory reads like a room
full of armchairs.

## The item detail view

`/items/:itemId`. Every dashboard card is a link to it, so the click target is
the whole card rather than an affordance in a corner.

- **Placard layout** — photo, status and era as archival tags, serif title,
  condition notes, then the facts as a definition list. With no photograph the
  panel collapses to a slim band across the top instead of a tall empty column
  beside the text.
- **"Who's asked"** lists each claimant and the reason they gave, in the order
  they asked. It does two jobs: it gives a submitted comment somewhere to land —
  the form invites a reason, and a reason that vanishes teaches people not to
  give one — and on a contested item it is what makes the agent's mediation
  legible, since otherwise the claimants' names appear only inside the message
  text. Your own claim reads "You". Someone who claimed without commenting gets
  "Asked without saying why" rather than a blank row, because the form says
  nobody has to.
- **The thread** is the item-specific slice of the unified feed. Steward's own
  posts are sage-tinted with the mark beside the name: distinct, but a
  participant in the feed rather than a system banner.
- **The mediation post on a contested item is lifted** — clay left edge, more
  room, an "A way through" tag. This is the track's mediation behaviour made
  visible rather than buried as one more message.
- **Claiming** posts to `/items/{id}/claim` and then *refetches*. Claiming can
  flip an item to contested and make the agent post a mediation message, and
  neither is something the client can predict — so it re-reads rather than
  patching local state.
- Claim is offered on `unclaimed` and `contested` only. A third person asking is
  a real thing that happens; past that, the executor has already decided.

## Not built yet

The Message Center and the contested-resolution view.
