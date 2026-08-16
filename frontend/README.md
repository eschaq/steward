# Steward — frontend

React + Vite + TypeScript, with react-router-dom. Six screens: sign-in, the
inventory dashboard, the item detail view, the Message Center, the contested
resolution screen and the executor's review table. All are wired to the real
backend and real Firebase Auth — there is no mock data anywhere in here.

| Path                          | Purpose                                            |
| ----------------------------- | -------------------------------------------------- |
| `src/firebase.ts`             | Firebase client SDK; `API_BASE_URL`, `ESTATE_ID`    |
| `src/auth.tsx`                | `AuthProvider` / `useAuth`; plain-language errors    |
| `src/api.ts`                  | Backend calls with the ID token attached            |
| `src/types.ts`                | Item shape, and all six statuses with their meanings |
| `src/index.css`               | The design system as CSS custom properties          |
| `src/screens/SignIn.tsx`      | Email/password sign-in                              |
| `src/screens/Welcome.tsx`     | The one-time walkthrough a new member sees          |
| `src/screens/Dashboard.tsx`   | Inventory grid, status filters                      |
| `src/screens/ItemDetail.tsx`  | One item: placard, facts, claim action, where it goes, thread |
| `src/screens/MessageCenter.tsx` | The estate-wide unified feed, and composing to it |
| `src/screens/ResolveItem.tsx` | The executor's decision screen                    |
| `src/screens/Review.tsx`      | The executor's bulk review table                  |
| `src/screens/Family.tsx`      | Who else is here, and the invite form              |
| `src/components/`             | `AddItem`, `ItemCard`, `StatusChip`, `StatusMark`, `StatusFilters`, `StewardMark`, `Claimants`, `MessageThread`, `Disposition` |
| `public/brand/`               | Hero photography (greyscale; duotoned in CSS)       |
| `mockups/`                    | Design comps — not built, not served                |
| `verify.mjs`                  | Drives the real app in a real browser (Playwright)  |

## Arriving

`<Arrival>` wraps the signed-in routes. It asks `GET /estates/{id}/me` once; if
an invite is still pending it accepts it — there is nothing to decide, the
person already followed the link — and if that acceptance is what flipped the
invite, they are new here and get shown around.

**"Once" is the server's answer, not a stored flag.** `POST /accept` returns
`first_accept`, true only for the call that actually flipped `accepted_at`.
EstateMembership's fields are fixed by the data model doc, and "have they been
welcomed" was already answerable from whether the invite was pending, so no new
field was invented. Every later sign-in accepts nothing and lands on the
dashboard. The trade-off worth naming: someone who reloads mid-walkthrough
doesn't get it back — a reload reads as a skip. For a first-run walkthrough
that's the right way round, and skipping is an offered option anyway.

A failed `/me` here doesn't put a wall in front of the app. Each screen asks for
its own standing and says plainly what it finds; the gate just gets out of the
way.

## The welcome

Three steps for everyone, four for an executor. On Ink, like sign-in — DESIGN.md
reserves the dark surface for arrival moments, and this is the other one.

The order is deliberate: what this is, then the thing they'll do first (ask for
something), then the thing they're most likely to be afraid of (someone else
asking too). *"It happens, and it isn't a fight."* That reassurance has to land
before they meet a contested item, not after. The executor's fourth step says
the final call is theirs to record and that Steward suggests but doesn't decide.

- **The estate names itself.** "This is Seed Estate", pulled from
  `me.estate_name`, falling back to "the estate" rather than a document id.
- **Skippable from every step** — "Skip, I'll figure it out". Some people just
  want to go and look at the list.
- **Place-markers, not a progress bar.** Three dots, no percentage, nothing to
  complete. Counts are a ledger, not a score.

## The screens

| Route             | Screen         | What it does                                    |
| ----------------- | -------------- | ----------------------------------------------- |
| —                 | Sign-in        | Email/password against Firebase Auth. Shown whenever nobody is signed in; not addressable. |
| `/`               | Dashboard      | The estate's inventory: ledger blocks, all six status filters, the item grid. |
| `/items/:itemId`  | Item detail    | Placard, who's asked and why, the item's message thread, and the claim action. |
| `/messages`       | Message Center | The estate-wide unified feed, and composing to it. |
| `/items/:itemId/resolve` | Contested resolution | Executor-only: record how a claimed or contested item was settled. |
| `/review`         | Review table   | Executor-only: every item on one page, grouped by what needs deciding. |
| `/family`         | Family         | Who's here and who's still waiting; the executor can ask someone new in. |

All six are wired to the real backend against real Firestore. There is no mock
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

## Where it goes — disposition, and the marketplace suggestion

On the item detail view, below the claimants. A resolved item with no
disposition shows the executor three choices — **Give it away / Sell it / Let it
go** — each with a line saying what it means. Once decided, the controls are
replaced by a sage panel stating where the piece is headed, read back from the
stored Disposition. Same completed-state pattern as the resolution screen, for
the same reason: a recorded decision should read as a fact, not as a form that
happens to be filled in.

- **It lives on the item page, not a route of its own.** Unlike a contested
  resolution, this decision needs no weighing of people — the item is already
  settled. Sending the executor somewhere else to press one of three buttons
  would be ceremony without a purpose.
- **Choosing "Sell it" asks Steward where in the same action.** A sell decision
  with no channel is a half-finished thought, so the click records the
  disposition *and* requests the recommendation, and the button says "Asking
  Steward where…" while the second call is out. Making that a separate button
  would leave a listing nobody knew to ask for.
- **The recommendation names the item, not the category.** It comes back from a
  real Gemini call — platform, one plain sentence about *this* piece, a suggested
  price, and a draft title and description the family could post as written.
  Platform names read as brands (`eBay`, `Facebook Marketplace`), not shouted in
  the uppercase every other tag uses.
- **The price says what it is.** "$45 — a starting point, not an appraisal."
  Whole dollars, because cents on a suggested asking price pretend to a precision
  nobody has.
- **The draft is offered, not imposed.** "The listing, if you want it", and under
  it "Yours to change before it goes anywhere. Steward has said what's worn or
  missing — that stays in." The description names the damage; that is the one
  part worth defending if the family edits it down.
- **A gap is stated, not hidden.** If the price and wording come back unusable,
  the panel says "No price or wording came back for this one — worth writing it
  yourself" rather than leaving three empty fields.
- **Beneficiaries see the decision, never the controls.** Where a piece is headed
  is family news; deciding it is not. The offer is gated on
  `GET /estates/{id}/me`, and `require_role` still decides the write.
- **The dashboard card shows the decision once there is one**, in place of
  "Leaning donate". `ItemSummary.decided_channel` comes from the same batched
  read the review table uses, so this is not a request per card. The suggestion
  is Steward's reading of a photo; once the executor has decided, that decision
  is the fact and the guess it replaced stops being shown.

Verified end-to-end in a real browser: a sell decision recorded through the UI on
a resolved demo item, the eBay recommendation rendered from a live Gemini call,
and a reload showing the recorded decision rather than the controls again.

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

**A fifth column, "Where it goes", on the settled and on-its-way groups only** —
those are the only items that have anywhere to go yet, so it does not sit empty
above the rest. A decided row names its destination ("Given away", "Let go",
"Sold via eBay" — the platform when Steward has recommended one, plain "Sold"
when it hasn't). An undecided one links into the item instead: settled with no
disposition is the last thing in this table still asking something of the
executor, so it gets a prompt rather than a blank cell.

It rides on the same composed `/review` request — the endpoint now batches
dispositions and their listings alongside claims and resolutions, so the column
costs no extra round trips.

The nav link is shown to everyone; the screen itself explains that working
through the estate this way is the executor's job, and points a beneficiary back
to the inventory. Hiding the link would leave them wondering what they were
missing.

## Asking someone in

`/family` — a screen of its own rather than a modal on the dashboard, because
the list is a standing thing an executor comes back to ("has she signed in
yet?"), not a one-off action. It's also the fourth place the redesign always
had, next to Inventory, Messages and Review.

Everyone reads the list; only the executor sees the form. Two groups, **Waiting
to come in** and **Here** — a pending invite is a real answer, not a missing
one, and the executor's actual question is which of those two a person is in.

The form sends `create_account: true`. The endpoint defaults it off so a script
can't quietly mint accounts; from the UI, filling in this form *is* the
deliberate act that guard exists for.

### What actually happens to the person you invited

An invite creates a Firebase Auth account with **no password** — which also
means the address can no longer be self-registered — and then emails them a real
link to set one. They follow it, sign in, `<Arrival>` accepts the waiting
invite, and the welcome runs.

**The confirmation reports what actually happened**, because the server tells
it. A send that worked says an email is on its way; a send that failed says so
in the same breath as confirming the invite is safely recorded, and drops the
sage treatment — a courtesy that didn't happen isn't a success. The executor is
the only fallback, so they have to know when they're it.

The sign-in screen keeps **"Forgot your password?"** — *"Just been invited? Put
your email above and use that link — it's how you set a password the first
time."* That is the way in if the email never arrives or the link goes stale.

## Responsive behaviour

Audited 2026-08-16 at **375 / 768 / 1280** with real device emulation
(`isMobile`, `hasTouch`), measuring overflow and tap-target geometry rather
than reading the CSS and assuming. Findings per screen:

| Screen | Found | Fixed |
| --- | --- | --- |
| Sign in | nothing | — |
| Dashboard | **nav clipped at 375** | nav wraps |
| Item detail | nav clipped at 375 | nav wraps; the two-column placard already collapsed at 820 |
| Message Center | nav clipped at 375; `msg__about` 17px tall | nav wraps; target ≥24 |
| Review table | **every cell unlabelled below 820** | column headings carried onto each cell |
| Family | nav clipped at 375 | nav wraps |

**The nav was the real breakage.** `.hero` is `overflow: hidden` — it clips the
gable photograph — so when the four links exceeded 375px the fourth one,
**Family, was cut off the right edge and unreachable**. Not cramped: gone. The
nav now wraps to a second line. Wrapping rather than a side-scrolling strip,
because a strip you have to swipe hides where you can go, and knowing where you
can go is the one thing an app bar is for.

**The review table was already stacking at 820px** — but with
`thead { display: none }`, which removed the column headings and left every
value unlabelled. "Given away" with nothing saying which column it was; "2
people" and "90% sure" survived only because they happen to describe
themselves. The heading is now visually hidden rather than removed (keeping
table semantics for a screen reader) and each cell carries its own label
through `data-label` + `::before`.

The 820px boundary is measured, not chosen: at 860px the four columns are
283/134/183/210 and a row is 80px tall; at 820px they collapse to nothing and
the row becomes 292px. The table has already stopped being a table by then.

**Cards, not horizontal scroll or column-hiding.** This is the screen an
executor *works through*; swiping left and right inside a row to decide
something is the opposite of unhurried. And the columns that would be hidden —
who asked, what was decided — are exactly the ones the decision needs. Nothing
is dropped; it reads downward instead.

The `Decided` label is conditional in the same way the desktop header is: on a
contested group the last cell holds a *Talk it through* button, and captioning a
button as a decision would be a lie.

**Tap targets.** Four inline links measured 15–21px against WCAG 2.5.8's 24×24
minimum — `review__link`, `msg__about`, `hero__crumb`, `estate-nav__mark` — all
of them the only route to somewhere. Each now has `min-height: 24px`, rising to
32 below 820 where the whole cell is the reach. Two `input`s still measure small
and are deliberately fine: the file input is visually hidden with its button as
the target, and the role radio sits inside a 273×118 label.

Verified after the fixes: **no horizontal overflow on any screen at any
breakpoint**, and every real target ≥24px.

## Accessibility — WCAG 2.1 AA

Ratios computed from the actual token values (WCAG relative-luminance formula,
`rgba` tokens flattened over their real backdrop), not eyeballed. 32 pairings
checked; 5 failed; all 5 fixed. Re-run: the audit script pattern is in the
commit that added this section.

**What failed and what it is now**

| Pairing | Was | Now | Needs |
| --- | --- | --- | --- |
| `outline` text on `surface` | 4.25 | **5.60** | 4.5 |
| `outline` text on `surface-lowest` | 4.46 | **5.89** | 4.5 |
| `outline` text on `surface-high` (unclaimed chip) | 3.64 | **4.80** | 4.5 |
| eyebrow (`outline`) on `surface` | 4.25 | **5.60** | 4.5 |
| input border on field fill | 1.55 | **3.11** | 3.0 |

Two token changes, both recorded in DESIGN.md: `outline` `#87736d` → `#71615c`,
and a new `field-border` `#988782` for control edges (`outline-variant` was
1.55:1 and stays as-is for decorative hairlines). Nothing else in the palette
moved — Ink, clay, sage and every status fill passed as written, because the
restraint in this design is in the fills and the text on them was already dark
enough.

Decorative hairlines sit at ~1.24:1 and stay there. 1.4.11 covers the boundaries
of components and graphics needed to understand content; a divider between two
paragraphs is neither.

**Colour is never the only signal.** Each status chip carries a small drawn mark
— open ring, filled ring, two overlapping rings, tick, arrow, question mark —
so the six separate by shape as well as hue. Verified by rendering all six under
`filter: grayscale(1)`: still distinguishable. The marks are `aria-hidden`; the
chip's label already says the word.

**Screen readers.** Confirmed against the live accessibility tree in Chromium,
not read off the JSX — every screen was loaded and queried for interactive
elements with no accessible name:

```
Sign in    main:1 nav:0 header:0   unnamed controls: none
Dashboard  main:1 nav:1 header:1   unnamed controls: none
Item       main:1 nav:0 header:1   unnamed controls: none
Messages   main:1 nav:1 header:16  unnamed controls: none
Review     main:1 nav:1 header:1   unnamed controls: none
Family     main:1 nav:1 header:1   unnamed controls: none
```

The sixteen headers on Messages are each inside an `<article>`, so they are
element headers rather than sixteen banner landmarks — correct as written.

- **Every screen's wrapper is `<main>`**, so there is a main landmark to skip to.
  They were all `<div className="page">`.
- **Card titles moved `h3` → `h2`.** Under the page's `h1` they skipped a level,
  which makes heading-by-heading navigation lie about the structure.
- **`photoAlt()` in `types.ts`** builds the item photo's description from the
  classifier's own output — the thing and its era, then the first sentence of
  condition. The photo is the one thing on these screens a non-sighted reader
  cannot otherwise reach, and "item photo" tells nobody anything. Live:
  *"Photograph of a table lamp — brass, 1970s. Brass column lamp with a pleated
  shade."* Trimmed to one sentence because alt text is announced in a single
  breath; the full notes are in the body copy below.
- **The review table's thumbnail keeps `alt=""`** — the item's name is the very
  next thing in the cell, and describing it would make a screen reader say it
  twice.

#### Once you've already asked

The claim form is replaced by a plain statement — *"You've asked for this one"*,
with what you said — rather than staying live. It used to stay fully live, so a
second click filed a genuine second Claim document for the same person.

The data model allows repeat claims **on purpose** (a second one is usually a
revised comment, and status counts distinct claimants so it never escalates
anything). But a form that looks untouched is not someone deciding to ask twice
— it is someone who thinks the first click didn't register. The backend rule is
right; the UI was hiding it.

**No separate edit path was built.** Changing your comment means taking your
name back off and asking again, which the copy says out loud. Withdraw-then-
reclaim would otherwise have been the *implementation* of an edit button, and it
resets `claimed_at` — which decides the order the mediation message names people
in. Better to make that a visible choice than a hidden side effect.

## Taking your name back

The withdraw affordance lives on **your own row** in "Who's asked", not as an
action on the item — changing your mind, or standing aside so a sibling can have
something, is an ordinary thing to do rather than a decision about the object. A
quiet "Take back your name" opens a plain question: *"Take your name back off
this one? You can always put it down again later."* with **Yes, take it back** /
**Keep it**.

Afterwards the claimant list and the status chip both update from a refetch, with
no page reload — the server owns the 0/1/2+ rule, so the client asks rather than
computes.

**Another pre-existing bug this surfaced.** `CLAIMABLE_STATUSES` was
`['unclaimed', 'contested']` — `claimed` was missing, so once one person had
asked for something *nobody else could ask through the UI*. The contested flow,
which is the centre of the whole product, was only reachable by script. It now
mirrors the backend's own set.

### Getting it out of the house

Once a disposition exists, the "Where it goes" panel says how far along it
actually is and offers the next step — in the words of the thing that happens,
never the raw enum:

| Channel | pending → | in_progress → |
| --- | --- | --- |
| donate | Mark it as dropped off | Mark it as taken |
| discard | Mark it as taken out | Mark it as gone |
| sell | Mark it as listed | Mark it as sold |

The panel reads *"Not dropped off yet"* → *"Dropped off"* → *"Given away —
August 16, 2026"*, and the button disappears at the end because there is nothing
further to mark. Beneficiaries see the progress and never the button.

**The review table's "Where it goes" column now follows the tense too.** It used
to say "Given away" about something still sitting in the hall — the honest
failing of the first version. It now reads *To give away* → *Dropped off* →
*Given away*, and *To sell on eBay* → *Listed on eBay* → *Sold on eBay*.

## Taking one off the list

A quiet underlined "Take this off the list" at the **bottom** of the item page,
executor-only — an action nobody came here to take shouldn't sit above the thing
they did come for, or look like an invitation.

Clicking it swaps in a plain question, not a modal: *"Take this off the list? You
can still find it if you need to — nothing gets thrown away."* with **Yes, take
it off** and **Leave it**. Sage, not red: removing a duplicate photograph is
housekeeping, not a danger, and the brand has no alarm states.

Afterwards the page keeps working and says so — *"This one is off the list.
Everything said about it is still here… it just won't show up in the inventory or
the review table."* The status chip reads **Taken off the list**, with a ringed
strike-through mark.

`removed` is a real status with a real label but is **not** in `ITEM_STATUSES`,
which drives the dashboard filters, the ledger counts and the review groups — the
API never returns a removed item in a list, so a filter for it would be a chip
that is permanently zero. `ALL_ITEM_STATUSES` is the wider set that labels and
chips use; `isListedStatus()` is the narrower check for grouping.

## Adding a belonging

**"Add an item" on the dashboard, executor-only.** A file picker, then a real
wait, then the new item's own page.

- **The wait is named, in two parts.** "Sending the photo…" for the first beat,
  then "Steward is looking at it…" once the Gemini call is where the time is
  actually going. A spinner could mean anything; this says what is happening.
  Underneath: *"This takes a few seconds… No need to wait on it if you'd rather
  carry on."*
- **It lands on the new item, not back on the grid.** What Steward made of the
  photograph is the thing the executor just asked a question about, so it should
  be the thing they see — not a hunt through thirty-nine cards.
- **The file input is visually hidden but still focusable and labelled.**
  `display: none` would take it out of the tab order; the clip-rect pattern
  keeps it reachable, and the button next to it opens it.
- **The input resets on change.** Without that, picking the same file twice in a
  row fires no change event and the second upload silently never happens.

One photo, one item, one call. Uploading six things means six calls — a batch
endpoint is a different feature with different questions behind it.

## Photographs

The executor can attach a photo from the item detail view: the whole empty photo
panel is the control, because a small "choose file" button in the corner of a
large blank area is a smaller target than the blank area itself. Beneficiaries
see the photo but not the control.

The endpoint returns the updated item, so the picture appears without a refetch —
and the placard expands from its slim no-photo band to the full two-column
treatment on the same render. The same URL then shows on the dashboard card and
as a thumbnail in the review table, both fed from the item data those screens
already load.

**`photo_urls` is an array, and its first entry is not necessarily displayable.**
Classification records the local file it read (`file:///…`) and an uploaded photo
is appended *after* it, so `photo_urls[0]` renders "no photo yet" for an item that
has one. `firstPhoto()` in `types.ts` picks the first `http(s)` entry, and the
review endpoint does the same server-side. This was a real bug, found by
uploading to an item that had been classified.

## Not built yet

Nothing in Tier 1. Tier 2 (marketplace channel, pricing, listing drafts) and
Tier 3 remain out of scope.
