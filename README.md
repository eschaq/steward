# Steward

Steward is a multi-user estate belongings disposition agent — a tool for families and
executors working through the contents of an estate together. Rather than one person
tracking everything in a spreadsheet, Steward gives each participant a shared view of
the belongings, captures their preferences and claims on individual items, and uses an
agent to help work toward a disposition for each thing in the estate — who receives it,
what gets sold or donated, and what still needs a decision. The system is built as two
Cloud Run services: a static frontend and a backend API that hosts the agent logic.

## Live

Both services run on Cloud Run in `us-central1`, and the Firestore Security Rules
are deployed to production:

| | |
| --- | --- |
| **App** | https://steward-frontend-223877730603.us-central1.run.app |
| **API** | https://steward-backend-223877730603.us-central1.run.app |
| **Rules** | live since 2026-08-17 — see [Firestore Security Rules](#firestore-security-rules) |

Probe the API at `/health`; Cloud Run's own frontend swallows `/healthz`.

Every `VITE_*` value is baked in at **build** time, so the frontend's config is a
set of Docker build args rather than Cloud Run environment variables — see
`frontend/README.md`. Backend secrets live in Secret Manager. Rules go up with
`firebase deploy --only firestore:rules`.

## Project layout

| Path        | Purpose                                                        |
| ----------- | -------------------------------------------------------------- |
| `frontend/` | React + Vite app — every signed-in screen. See `frontend/README.md`. |
| `backend/`  | API + ADK agent logic, deployed as a Cloud Run service. See `backend/README.md`. |
| `docs/`     | Planning and design documents.                                  |
| `firestore.rules` | Firestore Security Rules — see below.                     |
| `rules-tests/` | Emulator tests for those rules.                              |

## Setup

### Prerequisites

- Python 3.11, Node 20
- `gcloud` CLI authenticated against `steward-hackathon-505217`
- Application Default Credentials — Firestore, Auth, and Vertex AI all use them:
  ```bash
  gcloud auth application-default login
  gcloud auth application-default set-quota-project steward-hackathon-505217
  ```
- JDK 21+ only if you're running the Security Rules tests

### Local development

Two terminals.

```bash
# Backend — http://localhost:8000
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python init_firestore.py          # once, seeds one doc per collection
.venv/bin/uvicorn api:app --reload --port 8000
```

```bash
# Frontend — http://localhost:5173
cd frontend
npm install
cp .env.example .env.local                  # fill in with:
                                            #   firebase apps:sdkconfig WEB \
                                            #     --project steward-hackathon-505217
npm run dev
```

Sign in as a seeded test user, e.g. `steward-test-executor@example.com`. See
`backend/README.md` for how the test accounts and their passwords are set up.

The backend allows CORS from `localhost:5173` by default; set
`STEWARD_ALLOWED_ORIGINS` (comma-separated) when the frontend moves elsewhere.

## Firestore Security Rules

`firestore.rules` mirrors the access model `backend/membership.py` already
enforces with `require_role()`. Default is deny: a collection with no match block
is unreachable from a client, so a new collection has to opt in.

| Collection           | Read                        | Write                                    |
| -------------------- | --------------------------- | ---------------------------------------- |
| `users`              | your own document           | never (backend only)                     |
| `estates`            | accepted members            | executor (update only; no client create) |
| `estate_memberships` | your own row, or the roster | executor                                 |
| `items`              | accepted members            | `status` only — the claim triad to any member, `resolved`/`routed` to the executor alone |
| `claims`             | accepted members            | beneficiary, for themselves; delete your own |
| `messages`           | accepted members            | append-only, authored as yourself        |
| `resolutions`        | accepted members            | executor                                 |
| `dispositions`       | accepted members            | executor                                 |
| `override_logs`      | accepted members            | executor                                 |

A few consequences worth knowing:

- **A pending invite grants nothing.** `accepted_at` must be non-null, the same
  rule `get_role()` applies — but an invitee can always read *their own* row, so
  the invite is discoverable.
- **`ai_*` fields and `suggested_disposition` are unwritable by any client.**
  They come from Gemini and from the estate's OverrideLog history, not from a
  person. `hasOnly(['status'])` is what stops an `ai_category` edit riding along
  with a legitimate status change.
- **Messages can't be forged.** `user_id` must equal the caller, so a client
  can't post as `steward-agent` and put words in Steward's mouth.
- **Accepting an invite goes through the backend.** Only the executor can write a
  membership row, so a client can't set its own `accepted_at`. That matches
  `accept_invite()` today; if the frontend ever needs to self-accept, it needs a
  deliberate carve-out.
- **A status change can't smuggle a decision.** Moving an item between
  `unclaimed`, `claimed`, `contested` and `needs_clarification` is open to any
  member, because those are *derived* from claims that member is already allowed
  to write — nothing is forged that claiming wouldn't have achieved. `resolved`
  and `routed` are decisions, and decisions are the executor's. `removed` is in
  neither list: taking an item off the list has side effects, so it goes through
  `POST /items/{id}/remove`.

### Testing the rules

```bash
cd rules-tests
npm install
npm test          # firebase emulators:exec --only firestore "node rules.test.mjs"
```

52 cases against the emulator, covering each collection plus cross-estate
isolation, a pending invitee, a stranger, and an unauthenticated caller. Requires
a **JDK 21+** on PATH (firebase-tools refuses older) — Debian 12's
`default-jre-headless` is 17, so a Temurin 21 runtime is installed at
`/opt/java` and linked into `/usr/local/bin/java`.

### These rules are live, and writing them found a real hole

Deployed to production on **2026-08-17** and enforcing since. Nothing had ever
been released before that, which the releases API said plainly by returning
nothing at all.

Writing the tests is what found the vulnerability. The item `status` rule
originally checked **membership only** — so any beneficiary could write
`resolved` or `routed` straight into Firestore and forge a settlement the API
would have refused them. `resolve_item` and `record_disposition_decision` both
require the executor role; the rule did not, and the gap between those two
statements was the bug. It is now split by role, with four cases pinning the
behaviour: a beneficiary cannot settle an item, cannot mark one on its way, the
executor can, and nobody removes an item from the client at all.

The backend still uses the Admin SDK, which bypasses rules by design — that is
the trust boundary the two-service split exists to hold. These rules are what
stands behind it if a client ever reaches Firestore directly, and they are
enforced in production rather than aspirational.

## Status

**Tier 1 is complete, Tier 2 is built, and everything below is live in
production.** No mock data anywhere — every screen talks to the real API against
real Firestore.

**The core arc.** Photograph an item and Gemini classifies it; family members
claim what matters to them; a second claim makes an item contested; the executor
records how it was settled and where it goes. Items can be added from the UI,
soft-deleted, withdrawn from, and advanced through `pending → in_progress →
completed`.

**Three agent behaviours**, all writing into the same message feed the family
uses:
- **Clarifying questions** when classification confidence is low — and the
  family can answer, which sends the item back through Gemini with their words.
- **Contested-item mediation** the moment an item flips to contested.
- **Noticing a shared memory** — when someone posts a genuine recollection,
  Steward asks the others for one of their own. Once per item, ever.

**The adaptive loop, and a way to audit it.** Every executor override is logged
per estate and weights the next suggestion in that category. *What Steward has
learned* shows the same arithmetic back to the family, so the agent's claim that
"this estate has given away 3 of 4" is checkable rather than asserted.

**How things have landed** — a per-person view of roughly what each family
member has ended up with. Ordered by name and never by amount, no bars or
percentages, and explicit about what it is not counting. Deliberately not a
scoreboard.

**Accounts and estates.** Self-serve sign-up, invitation by email over Gmail
SMTP, and a first-run walkthrough for anyone arriving on an invite. One account
can hold several estates, switch between them from the estate name in the
header, start another, and remove one that was never used.

**Tier 2** adds a marketplace listing per item routed to sale — platform, why
that platform, a rough price and draft listing copy, in one Gemini call. **Tier 3**
(bulk auction batching) remains deliberately out of scope.

Verified with twelve backend suites against real Firestore, 52 Security Rules
cases against the emulator, and real-browser runs against the deployed services.

## License

**All rights reserved** — see [LICENSE](LICENSE). This repository is public so
the work can be read and judged; that is not permission to copy, reuse, or
build on it. Third-party assets keep their own terms, including the CC BY 2.0
photograph documented in [frontend/mockups/CREDITS.md](frontend/mockups/CREDITS.md).
