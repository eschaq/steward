# Steward — Project Context

Multi-user agent for estate belongings disposition: classify household items from
photos, let beneficiaries claim them, mediate contested claims, and adapt disposition
suggestions per estate based on executor overrides. Built for the All Things Agentic
Hackathon (Collaborative Partner track). Deadline: Aug 31, 2026.

## Reference docs — read on demand, don't load upfront

- `docs/estate-agent-RDD.md` — full scope, demo arc, tier boundaries, prize tracks.
  Check this for any scope question ("is X in or out").
- `docs/estate-agent-data-model.md` — exact schema for every entity. **Read this
  before creating or modifying any entity.** Don't invent fields or tables.
- `docs/estate-agent-branding.md` — tone/voice/palette. **Read this before writing
  any user-facing copy or UI.**
- `docs/design/steward/DESIGN.md` — the design system, and **the authority on
  visual style**. Kept in step with `frontend/src/index.css`; read it before
  building any frontend UI.
- `docs/design/{inventory_dashboard,item_detail_view,message_center,contested_resolution}/`
  — the original Stitch mockups (`code.html` + `screen.png`). Useful for
  *structure* and for the screens not yet built. **Superseded on visual style**
  by the "Hearth & Archive" revision in DESIGN.md — don't match their colours,
  radii, or chrome.

## Stack — locked, do not relitigate

- Gemini 3.5 (mandatory hackathon requirement), reached through **Vertex AI** via
  the `google-genai` SDK on Application Default Credentials — no API keys. Blaze
  billing is active; the old AI Studio key path and its 20-req/day free-tier cap
  are gone. Vertex serves `gemini-3.5-flash` from `global`, not a named region.
- Google ADK for agent orchestration
- Cloud Run — **two services**, frontend and backend split. Frontend never touches
  Firestore/Storage directly — only through the backend API.
- Firestore (multi-user real-time state), Firebase Auth (executor/beneficiary roles),
  Cloud Storage (item photos)
- Invitation email over Gmail SMTP (`GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` in
  `backend/.env`) — no third-party mail service. Best-effort: a failed send
  never blocks the invite.
- Gemini Flash by default; reserve Pro only for complex final reasoning

## Tier discipline — IMPORTANT

Only build **Tier 1** unless explicitly told otherwise. Tier 1 is the complete,
demoable core: classify → claim → contest → resolve → mark disposition intent,
including the Message Center and its three agent behaviours (clarifying
questions, contested-item mediation, noticing a shared memory) and the OverrideLog adaptive-suggestion loop.

**Do not build Tier 3 (bulk auction batching) without being explicitly asked.**
Tier 2 (marketplace listings) was asked for and is built. These attach later at the Disposition
table seam — see data model doc. Silently promoting stretch/deferred scope to core
is exactly the failure mode to avoid here.

## Brand — locked

Warm, unhurried, plainspoken. A quiet, steady hand at a kitchen table — not a
reseller-hustle app, not clinical/legal-tech. Concretely:
- No urgency badges, countdown timers, or gamification anywhere. Counts are a
  ledger, not a score — no bars, no targets, no percent complete. A zero goes
  quiet rather than rendering big in a strong color.
- Status colors are deliberately desaturated, not alarm-driven. All six item
  statuses the family sees have a tone — see DESIGN.md; don't invent one.
  (`removed` is the seventh and is never rendered.)
- No stock imagery — not "family holding hands", not stock interiors either.
  A photo slot gets the family's own photo or a tonal wash.
- No shadows anywhere. Depth is tonal layering and 1px hairlines.
- Palette: warm clay/terracotta primary, soft sage secondary, warm cream accent.
  Plus **Ink** (#211a14), a warm near-black used *only* for arrival moments
  (sign-in, the estate hero). This is not a dark mode and nothing toggles.
- Shape: chips are archival tags at 3px and never pills; actions always are.

## Failure handling principle

Every failure mode should degrade to a visible, honest agent statement — never a
silent guess or a blocked flow. Examples already decided (see RDD for full list):
- Classification fails → item falls back to `needs_clarification` with a plain
  "couldn't classify — take a look?" message, not a blocked upload.
- Simultaneous claims race → both get recorded; 2+ claims already means
  `contested` by design, so this is correct behavior, not a bug to prevent.
- OverrideLog is empty/fails → agent falls back to raw confidence and says so
  explicitly ("no pattern yet for this estate"), never fails silently.

## Known gotchas / tripwires

- **IMPORTANT:** OverrideLog does simple category-based override counting, not
  semantic/vector retrieval. Don't add vector search infrastructure — it's an
  explicit non-goal per the hackathon's own cost-saving guidance.
- **IMPORTANT:** Don't touch Firestore/Storage from the frontend service directly.
  All access goes through the backend API — this is the trust boundary the two-
  service split exists to enforce.
- Claim table intentionally has no uniqueness constraint. Don't "fix" this by
  adding one.
- Message table is a single unified feed (item-specific + general), not split by
  scope. `item_id` is nullable by design — don't split into separate tables.

## Commands

```bash
cd backend  && .venv/bin/uvicorn api:app --reload --port 8000   # API
cd frontend && npm run dev                                      # :5173 (or :5174)
cd backend  && STEWARD_ALLOW_DESTRUCTIVE_TESTS=1 \
              .venv/bin/python test_<name>.py                  # one suite, real Firestore
cd backend  && .venv/bin/python seed_demo_items.py              # demo inventory
cd frontend && node verify.mjs                                  # drive the real app in Chromium
cd rules-tests && npm test                                      # Security Rules (needs Java 21)
```

Per-directory detail lives in `backend/README.md` and `frontend/README.md` —
endpoint list, test-account setup, and the `/opt/java` note among them.

## State of play

- **Backend is built and verified end-to-end** against real Firestore: all Tier 1
  entities, all three agent behaviours, the OverrideLog loop, an ADK layer, and an
  authenticated FastAPI app. Twelve test scripts, all passing.
- **Items can be created from the UI.** `POST /estates/{id}/items` takes one
  photograph, classifies it, and writes the Item — the demo arc's entry point.
- **The frontend is past scaffolding.** Sign-in, the inventory dashboard, item
  detail, the Message Center, and the contested-resolution screen are built and
  working end-to-end against the real API — not mocks. **Tier 1 is complete.**
- **Tier 2 is built**, on explicit request: `marketplace.py` drafts a full
  listing — platform, why, a suggested price and draft title/description — in
  one Gemini call, shown on the item page. Tier 3 remains out of scope.
- **The backend is deployed**: https://steward-backend-223877730603.us-central1.run.app
  (Cloud Run, us-central1, min 0 / max 5, secrets in Secret Manager). Probe
  `/health` — Cloud Run's frontend swallows `/healthz`.
- **Firestore Security Rules are live in production** (deployed 2026-08-17;
  nothing had ever been deployed before). Verified by direct client reads, not
  just the emulator.
- **The frontend is deployed**: https://steward-frontend-223877730603.us-central1.run.app
  (min 0 / max 3, nginx serving a Vite build). `VITE_*` values are Docker build
  args, not runtime env. Both services are live and talking to each other.
- **Self-serve sign-up and estate creation are live.** `POST /estates` +
  `GET /me/estates`; the frontend routes on estate count. One account can hold
  several estates: the estate name in the hero is a switcher, and
  `/estates/new` starts another from inside the first. The chosen estate is
  kept in localStorage and honoured on reload *if* the account still belongs to
  it — membership is re-checked, never trusted from the browser.
- **An estate that was never used can be removed.** `DELETE /estates/{id}`,
  executor-only, and only while genuinely empty — no items (including `removed`
  ones), no messages, nobody else invited. `EstateStatus.CLOSED` is for a
  finished estate that keeps its history and is still unused by any code path;
  don't conflate the two.

## Notes

- This file stays under ~150 lines on purpose. If it's growing, move detail into
  `/docs` and leave a pointer here instead of pasting content in.
