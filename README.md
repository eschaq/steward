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
| `frontend/` | Static build, deployed as a Cloud Run service. *(placeholder)*  |
| `backend/`  | API + ADK agent logic, deployed as a Cloud Run service. See `backend/README.md`. |
| `docs/`     | Planning and design documents.                                  |
| `firestore.rules` | Firestore Security Rules — see below.                     |
| `rules-tests/` | Emulator tests for those rules.                              |

## Setup

> **Placeholder** — these steps are stubs to be filled in once the services exist.

### Prerequisites

- [ ] Node version — TBD
- [ ] Python version — TBD
- [ ] `gcloud` CLI, authenticated against the project — project ID TBD
- [ ] Firebase project / credentials — TBD

### Local development

```bash
# 1. Clone
git clone <repo-url> && cd steward

# 2. Frontend — install and run dev server
# TBD

# 3. Backend — create virtualenv, install deps, run API locally
# TBD

# 4. Environment variables — copy the example file and fill in values
# TBD
```

### Deploy

```bash
# Build and deploy each service to Cloud Run
# TBD
```

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

Backend is built and verified end-to-end against real Firestore: the Tier 1
entities, the two agent behaviors, the adaptive suggestion loop, an ADK agent
layer, and a minimal FastAPI app. Frontend is still a placeholder.

## License

[MIT](LICENSE)
