# Steward — frontend

React + Vite + TypeScript, with react-router-dom. Four screens: sign-in, the
inventory dashboard, the item detail view, and the Message Center. Both are wired to the real backend and real Firebase Auth — there is
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
| `src/screens/MessageCenter.tsx` | The estate-wide unified feed, and composing to it |
| `src/screens/ResolveItem.tsx` | The executor's decision screen                    |
| `src/screens/Review.tsx`      | The executor's bulk review table                  |
| `src/components/`             | `ItemCard`, `StatusChip`, `StatusFilters`, `StewardMark`, `Claimants`, `MessageThread` |
| `public/brand/`               | Hero photography (greyscale; duotoned in CSS)       |
| `mockups/`                    | Design comps — not built, not served                |
| `verify.mjs`                  | Drives the real app in a real browser (Playwright)  |

## The screens

| Route             | Screen         | What it does                                    |
| ----------------- | -------------- | ----------------------------------------------- |
| —                 | Sign-in        | Email/password against Firebase Auth. Shown whenever nobody is signed in; not addressable. |
| `/`               | Dashboard      | The estate's inventory: ledger blocks, all six status filters, the item grid. |
| `/items/:itemId`  | Item detail    | Placard, who's asked and why, the item's message thread, and the claim action. |
| `/messages`       | Message Center | The estate-wide unified feed, and composing to it. |
| `/items/:itemId/resolve` | Contested resolution | Executor-only: record how a claimed or contested item was settled. |
| `/review`         | Review table   | Executor-only: every item on one page, grouped by what needs deciding. |

All four are wired to the real backend against real Firestore. There is no mock
data anywhere in here.

## Running it

Both servers, in two terminals:

```bash
# Backend — http://localhost:8000
cd backend
.venv/bin/uvicorn api:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Vite asks for **:5173** and falls through to **:5174** if something already
holds it — check what it prints, since the two are easy to confuse when a dev
server has been left running. The backend allows CORS from both by default; set
`STEWARD_ALLOWED_ORIGINS` (comma-separated) if you run the frontend elsewhere.

Copy `.env.example` to `.env.local` and fill it in —
`firebase apps:sdkconfig WEB --project steward-hackathon-505217` prints the
values. `.env.local` is gitignored; `.env.example` is not.

Sign in with a seeded test user, e.g. `steward-test-executor@example.com`
(password set by `backend/dev_tokens.py`).

Nothing is deployed. Cloud Run is separate, later work.

## Reaching it from a phone

Both servers bind to loopback by default, and this machine is a **ChromeOS
Crostini container** — its address (`100.115.92.x`) is on ChromeOS's internal VM
subnet, which nothing else on your Wi-Fi can route to. Three things have to
happen.

**1. Bind both servers to all interfaces.**

```bash
cd frontend && npm run dev:lan                                   # vite --host 0.0.0.0
cd backend  && .venv/bin/uvicorn api:app --host 0.0.0.0 --port 8000
```

**2. Forward the ports out of the container.** ChromeOS →
Settings → Advanced → Developers → Linux development environment →
**Port forwarding**. Add **5173** and **8000**. Without this the phone cannot
reach the container at all, whatever the servers are bound to.

**3. Browse to the Chromebook's own LAN address**, not the container's. Find it
under Settings → Network → your Wi-Fi → IP address; it will look like
`192.168.x.x`. Then on the phone: `http://192.168.x.x:5173`.

**The backend has to allow that origin.** CORS is an explicit allow-list, not
`*`, because credentials ride on the Authorization header:

```bash
cd backend
STEWARD_ALLOWED_ORIGINS="http://localhost:5173,http://192.168.x.x:5173" \
  .venv/bin/uvicorn api:app --host 0.0.0.0 --port 8000
```

Notes from getting this working:

- **Leave `VITE_API_BASE_URL` blank.** The app derives the backend from whatever
  host you browsed from, port 8000. Hardcoding `http://localhost:8000` is the
  classic failure here — on the phone, `localhost` is the phone.
- **Firebase email/password sign-in works from any origin.** Verified over a
  non-localhost address; the Authorized Domains list governs OAuth redirect
  flows, not this.
- **A CORS rejection and a dead backend look identical to `fetch`** — both throw
  the same TypeError. The error banner names both causes and prints the origin
  to add, rather than confidently blaming the wrong one.
- Plain HTTP over the LAN, so no camera or geolocation later without HTTPS.
  Nothing needs them yet.

## What you are looking at when you test

The estate holds three kinds of item, and they are told apart by their document
id prefix. This matters when judging whether the app is behaving:

| Prefix  | Where it came from | Trust the `ai_*` fields? |
| ------- | ------------------ | ------------------------ |
| `demo-` | `backend/seed_demo_items.py`, **hand-written** | No. Categories, condition notes, era/brand and confidence were typed by a person to make the dashboard look like a real estate. None of it went through Gemini. |
| `test-` | the backend verification suites | No. Near-identical fixtures, mostly armchairs. |
| anything else | the real pipeline, `classify.py` → `items.py` | Yes — genuine Gemini output. |

So a `demo-` item showing 44% confidence is not the classifier being unsure; it
is a number chosen to give the UI a realistic spread. The **agent messages on
those items are real**, though — the seed script runs the actual ADK behaviours,
so the mediation on `demo-writing-desk` genuinely names its two claimants.

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

## The Message Center

`/messages`, reachable from the nav in the dark hero on every signed-in screen.

**One feed, not two.** Item-specific and general discussion are interleaved by
time, because the data model keeps them in a single collection with a nullable
`item_id`. Splitting them into tabs here would rebuild exactly the separation
the data model avoids. The per-item thread on ItemDetail is the same data
filtered to one item — same `MessageThread` component, with `showItems` on in
the estate feed and off on the item page, where the item is the page you are
already on.

A message tied to an item carries a link naming it — *About the writing desk →*
— so the agent's "Sarah and David have both asked for this one" is one click
from the desk itself. A general post says *About the estate* rather than leaving
a gap, since a null `item_id` is a deliberate kind of message, not a missing
link.

Posting appends the server's own copy of the message rather than refetching: it
comes back with the author name and timestamp already resolved, so it appears at
once without a round trip that could reorder the feed underneath. The compose
button stays disabled until the feed has loaded — appending to a feed that isn't
there yet would replace it with the single message just posted.

## The resolution screen

`/items/:itemId/resolve` — **a route of its own, not a panel inside ItemDetail.**
Recording a resolution is a decision with consequences: it moves the item out of
the claim flow and makes it eligible for disposition. A distinct URL makes that a
deliberate act rather than something reached by scrolling, and gives the executor
something to come back to or open from a message. Nothing is duplicated to pay
for it — the claimant list, the mediation post and the status chip are the same
components ItemDetail uses.

- **Steward's suggestion sits above the form**, not below it, so the executor
  reads the mediation before choosing rather than scrolling past the controls to
  find it.
- **Each resolution type carries its own explanation.** The executor is choosing
  between four unfamiliar words at a hard moment; a bare radio label would leave
  them guessing what "rotation" means here.
- **The recipient is a picker of actual claimants**, never a free-text name. The
  backend independently requires the recipient to have claimed the item, so those
  are the only valid choices — and if there are none, the form says so and points
  at "Something else — your call" instead of failing on submit.
- **A beneficiary who lands here** sees the item, the suggestion and the
  claimants, plus a plain line saying only the executor can record the decision
  and pointing back to the item page. No broken form, no unhandled 403.
- **Once decided, the controls are gone**, replaced by a sage panel stating what
  was settled, any note, and who recorded it — read back from the stored
  Resolution, so it survives a reload.

Whether to *offer* the controls comes from `GET /estates/{id}/me`. Whether the
write is *allowed* is still decided by `require_role` server-side; the role check
in the UI only governs what is on screen.

## The review table

`/review` — every item on one page, grouped by what needs deciding: contested,
claimed, needs-a-look, unspoken-for, settled, on-its-way. That order is the
executor's working order, not the enum's.

**Where the inline action stops, and why.** A **claimed** item has exactly one
person's name on it — there is nothing to weigh, so the row settles it in one
click and says whose name it is. A **contested** item links out to
`/items/:id/resolve` instead. Settling that from a table would mean choosing
between two people without reading why either wants it or what Steward
suggested; speed is the wrong thing to optimise at that moment. The table exists
to clear the uncontroversial so there is time for the rest.

Settled rows show what was decided rather than sitting blank. Resolving refetches
the whole table, because it moves a row between groups and changes the counts
above it — neither of which the client should guess.

The nav link is shown to everyone; the screen itself explains that working
through the estate this way is the executor's job, and points a beneficiary back
to the inventory. Hiding the link would leave them wondering what they were
missing.

## Not built yet

Nothing in Tier 1. Tier 2 (marketplace channel, pricing, listing drafts) and
Tier 3 remain out of scope.
