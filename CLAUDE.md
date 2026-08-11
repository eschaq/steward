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

## Stack — locked, do not relitigate

- Gemini 3.5 (mandatory hackathon requirement)
- Google ADK for agent orchestration
- Cloud Run — **two services**, frontend and backend split. Frontend never touches
  Firestore/Storage directly — only through the backend API.
- Firestore (multi-user real-time state), Firebase Auth (executor/beneficiary roles),
  Cloud Storage (item photos)
- Gemini Flash by default; reserve Pro only for complex final reasoning

## Tier discipline — IMPORTANT

Only build **Tier 1** unless explicitly told otherwise. Tier 1 is the complete,
demoable core: classify → claim → contest → resolve → mark disposition intent,
including the Message Center and its two agent behaviors (clarifying questions,
contested-item mediation) and the OverrideLog adaptive-suggestion loop.

**Do not build Tier 2 (marketplace channel/pricing) or Tier 3 (bulk auction
batching) without being explicitly asked.** These attach later at the Disposition
table seam — see data model doc. Silently promoting stretch/deferred scope to core
is exactly the failure mode to avoid here.

## Brand — locked

Warm, unhurried, plainspoken. A quiet, steady hand at a kitchen table — not a
reseller-hustle app, not clinical/legal-tech. Concretely:
- No urgency badges, countdown timers, or gamification anywhere
- Status colors are deliberately desaturated (muted amber/green/gray), not alarm-driven
- No stock "family holding hands" imagery
- Palette: warm clay/terracotta primary, soft sage secondary, warm cream accent

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

TBD — fill in once package.json/build tooling exists for frontend and backend.

## Notes

- This file stays under ~150 lines on purpose. If it's growing, move detail into
  `/docs` and leave a pointer here instead of pasting content in.
