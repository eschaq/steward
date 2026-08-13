# Steward — frontend

React + Vite + TypeScript. Two screens so far: sign-in and the inventory
dashboard. Both are wired to the real backend and real Firebase Auth — there is
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
| `src/components/`             | `ItemCard`, `StatusChip`, `StatusFilters`           |
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

## Design

Tokens come from `docs/design/steward/DESIGN.md`, written as CSS custom
properties in `src/index.css` rather than a Tailwind config — the tokens are
already fully specified there, and a stylesheet keeps them in one place with no
build-time config to drift from the source of truth.

The brand rules out a lot on purpose: no shadows (depth is tonal layering and
1px "ghost borders"), no lift on hover (a tonal shift instead), no urgency, no
countdowns, no gamification. Status chips are rectangular with a soft radius —
"archival tag", not pill.

**Three status colours are mine, not the palette's.** `DESIGN.md` specifies only
contested (muted amber), resolved (faded green), and unclaimed (soft gray), and
the token list has no amber at all:

| Status                | Colour                              | Source                       |
| --------------------- | ----------------------------------- | ---------------------------- |
| `unclaimed`           | `surface-container-highest`         | palette                      |
| `claimed`             | `secondary-container` (sage)        | palette                      |
| `contested`           | `#f2e2c4` / `#7a5320`               | **derived** — muted amber    |
| `resolved`            | `secondary-fixed-dim`               | palette                      |
| `routed`              | `tertiary-fixed`                    | **derived** — quiet, done    |
| `needs_clarification` | `primary-fixed` (clay tint)         | **derived** — Steward is asking |

Worth a designer's eye before the demo.

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

## Not built yet

Item detail, the Message Center, and the contested-resolution view. There is no
router — two screens chosen by whether anyone is signed in. Cards deliberately
don't look clickable, since there is nowhere to click through to.
