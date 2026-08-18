# Steward

Steward is a multi-user estate belongings disposition agent — a tool for families and
executors working through the contents of an estate together. Rather than one person
tracking everything in a spreadsheet, Steward gives each participant a shared view of
the belongings, captures their preferences and claims on individual items, and uses an
agent to help work toward a disposition for each thing in the estate — who receives it,
what gets sold or donated, and what still needs a decision. The system is built as two
Cloud Run services: a static frontend and a backend API that hosts the agent logic.

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

### Deploy

Both services are live on Cloud Run in `us-central1`, and the Security Rules are
deployed to production:

- frontend — https://steward-frontend-223877730603.us-central1.run.app
- backend — https://steward-backend-223877730603.us-central1.run.app (probe
  `/health`; Cloud Run's own frontend swallows `/healthz`)

Every `VITE_*` value is baked in at **build** time, so the frontend's config is a
set of Docker build args rather than Cloud Run environment variables — see
`frontend/README.md`. Backend secrets live in Secret Manager. Rules go up with
`firebase deploy --only firestore:rules`.

## Firestore Security Rules

`firestore.rules` mirrors the access model `backend/membership.py` already
enforces with `require_role()`. Default is deny: a collection with no match block
is unreachable from a client, so a new collection has to opt in.

| Collection           | Read                        | Write                                    |
| -------------------- | --------------------------- | ---------------------------------------- |
| `users`              | your own document           | never (backend only)                     |
| `estates`            | accepted members            | executor (update only; no client create) |
| `estate_memberships` | your own row, or the roster | executor                                 |
| `items`              | accepted members            | `status` only, and only to a valid value |
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
- **Nothing here is load-bearing yet.** Every write currently goes through the
  Admin SDK, which bypasses rules entirely. These exist for the moment frontend
  code talks to Firestore directly — the boundary the two-service split holds.

### Testing the rules

```bash
cd rules-tests
npm install
npm test          # firebase emulators:exec --only firestore "node rules.test.mjs"
```

48 cases against the emulator, covering each collection plus cross-estate
isolation, a pending invitee, a stranger, and an unauthenticated caller. Requires
a **JDK 21+** on PATH (firebase-tools refuses older) — Debian 12's
`default-jre-headless` is 17, so a Temurin 21 runtime is installed at
`/opt/java` and linked into `/usr/local/bin/java`.

Rules have **not** been deployed to production. `firebase deploy` is a separate
decision.

## Status

**Tier 1 is complete, Tier 2 is built, and both services are deployed.** The
backend carries every Tier 1 entity, three agent behaviours (clarifying
questions, contested-item mediation, and noticing a shared memory), the adaptive
suggestion loop, an ADK layer and an authenticated FastAPI app, all verified
end-to-end against real Firestore. The frontend runs the whole arc against that
API — sign-in and self-serve sign-up, the inventory, item detail, the Message
Center, contested resolution, Review, and Family — with no mock data anywhere.
Tier 2 adds a marketplace listing draft per item. Tier 3 (bulk auction batching)
remains deliberately out of scope.

## License

[MIT](LICENSE)
