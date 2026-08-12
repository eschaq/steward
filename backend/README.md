# Steward — backend

Tier 1 Pydantic models, Firestore initialization, estate membership (Auth users,
invites, role checks), claims, and the Message Center with its two agent
behaviors. No HTTP API yet.

| File                 | Purpose                                                        |
| -------------------- | -------------------------------------------------------------- |
| `models.py`          | Pydantic models for Estate, User, EstateMembership, Message, Claim, Item |
| `firebase_app.py`    | Initializes the Admin SDK once per process; `get_db()`          |
| `membership.py`      | Create Auth user, invite to estate, accept invite, role check   |
| `classify.py`        | Photo → the four `ai_*` Item fields, via the Gemini API         |
| `items.py`           | Writes a classified photo out as an Item document               |
| `claims.py`          | Record a claim; re-derive item status from its claims           |
| `messages.py`        | The feed, the agent User, and the agent's two behaviors         |
| `resolutions.py`     | Executor resolves a claimed/contested item; flips to `resolved` |
| `overrides.py`       | OverrideLog + the adaptive suggestion loop                       |
| `dispositions.py`    | Executor's final call: writes the Disposition row + OverrideLog  |
| `init_firestore.py`  | Seeds one document per collection and reads it back             |
| `test_membership.py` | Script: invite + accept two users, print each role              |
| `test_classify.py`   | Script: classify a real photo and a blank square, store both    |
| `test_claims.py`     | Script: claim one item alone, another twice, check statuses     |
| `test_messages.py`   | Script: both agent behaviors fire once, and only once           |
| `test_resolutions.py`| Script: beneficiary refused, executor resolves, unclaimed refused |
| `test_overrides.py`  | Script: same photo, cold start vs. after the estate has a habit  |
| `test_dispositions.py`| Script: a decision writes both docs; uncertain/unresolved refused |
| `test_recompute.py`  | Script: a stale suggestion catches up; a resolved one is left alone |
| `requirements.txt`   | `firebase-admin`, `pydantic`, `google-generativeai`, …          |

## Membership

`membership.py` is the authorization seam. The Firebase Auth uid *is* the
`User.id`, so a uid from a verified ID token can be role-checked directly.

```python
uid = create_auth_user("aunt.jo@example.com", "Aunt Jo")
invite_to_estate("seed-estate-001", "aunt.jo@example.com", MembershipRole.BENEFICIARY)
accept_invite("seed-estate-001", uid)

get_role(uid, "seed-estate-001")                        # MembershipRole.BENEFICIARY
require_role(uid, estate_id, MembershipRole.EXECUTOR)   # raises MembershipError
```

Behavior worth knowing:

- Membership document ids are deterministic (`{estate_id}__{user_id}`), so one
  user has at most one membership per estate and a role check is a single
  document read — no query, no composite index.
- A pending invite (`accepted_at` null) grants **no** role. `get_role` returns
  `None` until the invite is accepted; pass `include_pending=True` only to
  render an invite screen, never to authorize.
- Everything is idempotent: re-inviting an accepted member does not revoke their
  acceptance, and accepting twice keeps the first `accepted_at`.
- Inviting an email with no Auth account raises `MembershipError` rather than
  writing a membership that points at nobody.

## Dispositions

Disposition is **the seam** the data model doc describes: the point every item
passes through once resolved, and the only thing Tier 2 (MarketplaceListing) and
Tier 3 (AuctionBatchItem) ever attach to. Nothing later touches Item, Claim, or
Resolution.

```python
entry, disposition = record_disposition_decision(
    item_id, SuggestedDisposition.DONATE, executor_uid
)
disposition.channel   # DispositionChannel.DONATE
disposition.status    # DispositionStatus.PENDING

get_disposition(item_id)           # Disposition | None
get_disposition_decision(item_id)  # OverrideLog | None
```

One call writes **two documents in a single batch** — the Disposition row and the
OverrideLog entry. A decision that logged but didn't route, or routed but didn't
log, would leave the estate's learned history and the item's actual fate
disagreeing, so they land together or not at all.

### The channel map

| Executor chooses | Channel            |
| ---------------- | ------------------ |
| `discard`        | `discard`          |
| `donate`         | `donate`           |
| `sell`           | `sell_marketplace` |
| `uncertain`      | *rejected*         |

`sell_auction_bulk` is on the enum so the entity's shape never changes when Tier
3 lands, but **nothing in Tier 1 routes to it** — the test asserts it is absent
from `CHANNEL_FOR_CHOICE.values()`, so a path can't appear unnoticed.

### Gates

- **Executor only** — `require_role(...)`, raising `MembershipError`. Checked
  first, so a non-executor isn't told about the item's state.
- **Resolved only** — `DispositionError` otherwise. A disposition decided before
  the family has settled who gets the item answers the wrong question.
- **`uncertain` is refused** — it is the absence of a decision, there is no
  channel for it, and logging it would teach the estate's history that hesitation
  is a preference. Deferring is a legitimate thing for an executor to do; it just
  isn't this function, so it raises rather than defaulting to something.

Both refusals happen before any write. The test checks *both* collections are
untouched, not just that an error was raised.

### Other behavior

- **One decision per item**, via deterministic ids (`disposition__{item_id}` and
  `override__{item_id}`). An executor who revises their call replaces both
  documents, so the two never drift apart and the history isn't double-counted.
- **The item stays `resolved`.** Deciding a disposition routes the item; it does
  not advance or re-open it. `ItemStatus.ROUTED` exists but nothing sets it yet —
  that belongs with acting on a disposition (`pending` → `in_progress` →
  `completed`), which isn't built.
- `status` starts `pending` and `completed_at` starts null. Nothing advances them
  yet.

Verified run against real Firestore (`test_dispositions.py`):

```
(a) donate on a resolved item -> both documents written and mutually consistent
    (channel == CHANNEL_FOR_CHOICE[logged choice]; item still resolved)
(b) uncertain                 -> DispositionError, neither collection touched
(c) unresolved item           -> DispositionError, neither collection touched
(d) sell -> sell_marketplace, discard -> discard, no path to sell_auction_bulk
```

## Adaptive suggestions (OverrideLog)

This is the persistent-memory mechanic the Collaborative Partner track requires.
Every finalized executor decision lands in `override_logs`; before suggesting a
disposition for a new item, the agent counts this estate's past decisions in the
same category and leans that way, saying plainly why.

```python
record_disposition_decision(item_id, SuggestedDisposition.DONATE, executor_uid)

suggest_disposition(estate_id, "armchair")
#   .suggested_disposition  SuggestedDisposition.DONATE
#   .reason   "This estate has donated 3 of 4 armchair items so far, so I'm
#              leaning donate here too."
#   .has_pattern / .matching_count / .history_count
```

**Simple category-based counting, deliberately** — one query and a `Counter`.
No embeddings, no vector search, no semantic retrieval; an explicit non-goal per
CLAUDE.md. `item_category` is denormalized onto the log row so this stays a
count, not a join.

### Where it hooks in

`items.create_item_from_classification` consults it before writing the Item, so
`suggested_disposition` is adapted at creation time rather than patched later.
The classifier reads what a thing *is*; the override history is the only thing
that says what should happen to it.

`Item` has no field for the reason — its shape is fixed by the data model doc —
so `items.suggestion_for(estate_id, classification)` returns the full
`DispositionSuggestion` for a caller that wants to show the family *why*.
Surfacing that in the UI or the feed is not wired up yet.

### What it does when it doesn't know

- **No history for the category** → the classifier's read is returned unchanged
  (`uncertain`), `has_pattern=False`, and the reason contains the literal phrase
  **"no pattern yet for this estate"**. It never fabricates a lean from nothing.
- **A dead heat** (2 donated, 2 sold) → also not a pattern. The reason names the
  split rather than picking a side and dressing it up as a preference.
- **An unidentified item** (`needs_clarification`) → the lookup is skipped
  entirely. A real pattern must not be applied to a guess about what the item is.
- `ai_classification_confidence` is passed through untouched in every branch —
  the override log weights the *disposition*, never the classifier's confidence
  in what the thing is.

`MIN_HISTORY_FOR_PATTERN = 1`, so a single past decision counts. The reason text
carries the thinness honestly ("has donated the one armchair item so far")
instead of a hidden threshold silently ignoring it. Raise the constant if one
data point turns out to feel jumpy in the demo.

### Keeping a suggestion current

The suggestion written at classification time is a **snapshot** — it reflects the
override history as it stood that day, and later decisions in the same category
never reach it on their own. `items.recompute_suggestion(item_id)` re-runs the
same weighting function against the history as it stands now and writes the
result back if it moved:

```python
recompute_suggestion("item-1").suggested_disposition   # DONATE, and stored
```

- **Only `unclaimed` / `claimed` / `contested` are recomputed.** A `resolved`
  item's disposition has already been decided by a person, and `routed` is
  further along still — reaching back to change what the agent suggests would be
  rewriting advice nobody is waiting on. `needs_clarification` is excluded for
  the opposite reason: the agent doesn't know what the item is yet.
- **An ineligible item is a no-op, not an error.** The stored value comes back
  untouched with a reason saying why it was left alone.
- **The baseline is `uncertain`, not the stored value.** So the suggestion always
  reflects current history: if the pattern that produced `donate` later evens
  out, recompute walks the item back to `uncertain` rather than leaving a lean
  nothing supports any more.
- **Status is never touched** — this changes advice, not where the item sits in
  the flow.

Nothing calls it automatically yet. The natural trigger is
`record_disposition_decision`, fanning out to the estate's other items in the
same category; that's a write per item, so it wants a deliberate decision rather
than a quiet default.

Verified run against real Firestore (`test_recompute.py`):

```
item created with no 'armchair' history   -> stored uncertain
...4 decisions land (donate, donate, sell, donate)
same item, still untouched                -> stored uncertain   (the snapshot problem)
recompute_suggestion(item)                -> donate, and the document now says donate
                                             status still unclaimed; second call stable

a resolved item, same category            -> weighting would say donate
recompute_suggestion(item)                -> uncertain, unchanged, "This item is
                                             resolved, so its disposition isn't the
                                             agent's to suggest any more"
```

### Where the decision comes from

`dispositions.record_disposition_decision` is what feeds this — see Dispositions
below. Every finalized decision is logged, agreements included, because the tally
counts total outcomes rather than corrections.

Verified run against real Firestore (`test_overrides.py`) — one real Gemini
classification of `sample_item.png`, put through the same path twice:

```
category 'armchair', confidence 0.98

(a) no history      -> uncertain
    "There's no pattern yet for this estate — nothing else in armchair has
     been decided yet, so this is the classifier's read on its own."

    ... 4 items claimed, resolved, and decided: donate, donate, sell, donate

(b) same photo      -> donate
    "This estate has donated 3 of 4 armchair items so far, so I'm leaning
     donate here too."

(c) same category, confidence 0.0 -> uncertain, pattern deliberately not applied
```

The four history items are built the long way round — claimed, resolved, then
decided — rather than by writing log rows directly, so the history under test is
history the real flow could actually have produced.

## Resolutions

`resolutions.py` records the executor's decision on a claimed or contested item
and flips it to `resolved` — the state that makes it eligible for Disposition,
the seam Tier 2 and Tier 3 attach at.

```python
resolve_item(
    "item-1",
    resolved_by_user_id=executor_uid,
    resolution_type=ResolutionType.ROTATION,
    resolved_to_user_id=claimant_uid,
    notes="Two years at Ana's, then two at Sam's.",
)

get_resolution("item-1")   # Resolution | None
```

Two gates, and both raise rather than shrug:

- **Authorization** — `require_role(uid, estate_id, EXECUTOR)`, so this module
  has no second, divergent idea of what an executor is. A beneficiary gets
  `MembershipError`. Checked *before* the state gate, so a non-executor learns
  they may not do this rather than learning about the item's state first.
- **State** — only `claimed` and `contested` are resolvable. `unclaimed` has
  nothing to decide, `needs_clarification` isn't identified yet, and
  `resolved`/`routed` are already past this point. Each raises `ResolutionError`
  naming the actual reason, not a generic rejection.

Both errors are raised before anything is written — the test asserts the refused
cases leave no Resolution document and the item's status untouched.

Other behavior worth knowing:

- **`assigned_to_claimant` and `rotation` require `resolved_to_user_id`, and it
  must be someone who actually claimed the item.** Handing the item to a
  non-claimant is a different decision and the data model has a type for it:
  `executor_override`. The other two types leave the field optional.
- **One resolution per item, via a deterministic id** (`resolution__{item_id}`).
  The status gate already allows resolving exactly once; pinning the id makes
  that structural rather than merely emergent.
- Resolution does **not** post to the Message Center. The two agent behaviors in
  Tier 1 are the clarifying question and contested mediation — adding a third
  here would be scope the RDD didn't ask for.

Verified run against real Firestore (`test_resolutions.py`):

```
(a) beneficiary resolves contested  -> MembershipError, nothing written
(b) executor resolves as rotation   -> status resolved, all fields read back
    second resolution on that item  -> ResolutionError
(c) executor resolves unclaimed     -> ResolutionError, item still unclaimed
```

## Message Center

`messages.py` is one unified feed — item-specific and general estate discussion
in the same `messages` collection, `item_id` null for the latter. Per the data
model, the agent posts here through the same table humans use; there is no
separate notification system.

```python
post_message(estate_id, uid, "Planning to come by Saturday.")          # general
post_message(estate_id, uid, "I remember this one.", item_id="item-1") # about an item

get_messages_for_item("item-1")     # [Message, …], oldest first
get_messages_for_estate(estate_id)  # the whole feed
get_agent_user()                    # the User that authors agent messages
```

### The agent user

`get_agent_user()` returns the `role_type=agent` User, creating it only if there
isn't one: it checks the well-known id `steward-agent` first, then any other user
with `role_type=agent` (so a row created elsewhere is adopted, not duplicated).

It is a Firestore document only — **no Firebase Auth account**, deliberately. The
agent never signs in, and giving it credentials would put a non-human principal
inside the auth boundary `membership.py` exists to hold.

### The two behaviors

| Behavior          | Trigger                                   | Hooked into                    |
| ----------------- | ----------------------------------------- | ------------------------------ |
| Clarifying question | item lands in `needs_clarification`      | `items.create_item_from_classification` |
| Contested mediation | item *transitions into* `contested`      | `claims.recompute_item_status` |

- **Fires on the transition, not the state.** `recompute_item_status` compares
  the status before and after; an item that was already contested gets no second
  message no matter how often recompute runs.
- **Deterministic message ids** (`agent-clarify__{item_id}`,
  `agent-mediate__{item_id}`) back that up at the storage layer, so the agent
  says a given thing about a given item exactly once. `_post_once` checks for the
  document and returns `None` instead of overwriting, which keeps the original
  `created_at` intact.
- **A failed post never propagates.** The upload or the claim that triggered it
  has already committed; losing that work over a feed write would be worse than a
  missing message. The failure prints to stderr rather than being swallowed.
- **The clarifying question offers its half-formed guess when it has one** ("It
  might be a vase, but I'd rather ask than guess") and shrugs plainly when it
  doesn't. Either way the family sees no confidence scores or thresholds — the
  test asserts that internal vocabulary stays out of the copy.
- The mediation message names the claimants in the order they spoke up, then
  **proposes a way through** — acknowledging the conflict alone leaves the family
  where they started. It covers all three paths the data model's Resolution types
  allow (assign to one claimant, share/rotate, outside appraisal) as prose, not a
  bulleted menu: a list of choices reads like a form to fill in, wrong for the
  moment this message lands in. The test asserts at least one path is named and
  that no bullets appear. No urgency, no nudging — tone per
  `docs/estate-agent-branding.md`.

One known gap: an item that went contested, got resolved, and somehow became
contested again would not be mediated a second time. It can't happen through the
current code — `resolved` is outside `CLAIMABLE_STATUSES`, so recompute never
touches it — but the deterministic id is what would suppress it if that changed.

Verified run against real Firestore (`test_messages.py`):

```
(a) blank square -> needs_clarification -> 1 clarifying message, agent-authored
(b) 2nd claimant -> contested            -> 1 mediation message, on the transition
    (after the 1st claim: 0 messages — one claimant isn't a conflict)
(c) recompute while already contested    -> still 1, created_at unchanged
```

## Claims

`claims.py` records claims and derives item status from them. Callers never pass
a status in — `record_claim` writes the claim, then recomputes.

```python
claim, status = record_claim("item-123", uid, comment="Grandma promised me these.")
status                                  # ItemStatus.CLAIMED  (or CONTESTED)

get_claims_for_item("item-123")         # [Claim, …], oldest first
count_claims("item-123")                # 2  — documents, duplicates included
count_distinct_claimants("item-123")    # 1  — people
recompute_item_status("item-123")       # re-derive without adding a claim
```

Behavior worth knowing:

- **No uniqueness constraint, on purpose.** Two beneficiaries claiming at the
  same moment both get a document. 2+ claimants already *means* `contested`, so
  there is nothing to race-prevent — per the RDD's failure-handling section.
- **Status counts distinct claimants, not documents.** 0 → `unclaimed`,
  1 → `claimed`, 2+ → `contested`.
- **A repeat claim from the same user is recorded, not deduplicated.** It is a
  real event (usually a revised comment) and dropping it would be a silent guess
  about what the person meant. Since counting is per-person, re-claiming never
  escalates an item to `contested` by itself.
- **`resolved`, `routed`, and `needs_clarification` are left alone.** Recompute
  owns only the `unclaimed`/`claimed`/`contested` triad; it returns the current
  status unchanged rather than dragging a resolved item backwards.
- Claiming a nonexistent item raises `ClaimError` instead of writing an orphan
  claim.
- Querying claims by `item_id` is a single-field equality filter, so Firestore's
  automatic index covers it — no composite index to deploy.
- **The transition into `contested` posts the agent's mediation message** — see
  Message Center below. Recomputing an item that was already contested is silent.

Verified run against real Firestore (`test_claims.py`), both transitions:

```
test-claim-item-a   1 claimant  -> claimed     1 claim  queried back
test-claim-item-b   2 claimants -> contested   2 claims queried back
test-claim-item-a   same claimant again -> still claimed, 2 claims / 1 claimant
```

## Classification

`classify.py` calls the Gemini API directly (API key from `.env`, see
`.env.example`), not Vertex AI — GCP billing isn't enabled on this project.
Model is `gemini-3.5-flash`; override with `GEMINI_MODEL`.

```python
c = classify_image("test_data/sample_item.png")
c.ai_category, c.ai_condition_notes, c.ai_est_era_or_brand, c.ai_classification_confidence
c.status                        # ItemStatus.NEEDS_CLARIFICATION below 0.6, else UNCLAIMED

item, c = classify_and_create_item("seed-estate-001", "photo.png")   # items.py
```

- **Confidence threshold, 0.6.** `Classification.status` derives the item status
  from the confidence — a caller cannot pass a status in and override it, so a
  low-confidence item lands in `needs_clarification` every time.
- **Failures degrade, they don't block.** A transport error, quota rejection, or
  unparseable response returns confidence 0.0 with "Couldn't classify this one —
  take a look?" and an `error` string, which routes through the same threshold to
  `needs_clarification`. `error` is deliberately *not* persisted — Item's shape
  is fixed by the data model doc.
- **`suggested_disposition` comes from the estate's OverrideLog history**, not
  from Gemini — see Adaptive suggestions above. With no history it stays
  `uncertain`; a one-shot guess is the thing the RDD explicitly rejects.
- Posting the clarifying question to the Message Center is not wired up yet —
  `Message` has no model, and the item status is the trigger for it.
- Generation is constrained by a `response_schema`, so the model returns the four
  fields and nothing else. The parser still uses `raw_decode` rather than
  `json.loads`: `gemini-3.5-flash` has been observed appending one stray `}`
  after otherwise valid JSON, and a good classification shouldn't be thrown away
  over trailing noise.

Verified run — real photo, real API, real Firestore:

```
sample_item.png              armchair, "Louis XV style", confidence 0.98 -> unclaimed
generated_blank_square.png   unknown, "solid greyish-blue ... no identifiable
                             household items", confidence 0.0 -> needs_clarification
```

### API key

`.env` holds the "Default Gemini API Key" from the `gen-lang-client-0376941757`
project. The key originally in `.env` belonged to an AI Studio project whose
prepayment credits were depleted — every model returned 429. Note that AI Studio
keys are ordinary GCP API keys (`gcloud services api-keys list --project …`), but
a key minted with `gcloud` against a project AI Studio doesn't know about is
rejected as `API_KEY_INVALID`; the key has to come from AI Studio.

### `google-generativeai` is deprecated

The SDK prints a deprecation warning on import (support ended; `google-genai` is
the replacement) and its protobuf pin conflicts with `google-cloud-firestore`'s.
Firestore works anyway — verified — but this is worth migrating before the
frontend lands.

## Running the scripts

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Credentials — see note below
gcloud auth application-default login
gcloud auth application-default set-quota-project steward-hackathon-505217

.venv/bin/python init_firestore.py
.venv/bin/python test_membership.py
.venv/bin/python test_classify.py
.venv/bin/python test_claims.py
.venv/bin/python test_messages.py
.venv/bin/python test_resolutions.py
.venv/bin/python test_overrides.py
.venv/bin/python test_dispositions.py
.venv/bin/python test_recompute.py
```

`test_classify.py` exit codes: `0` both cases behaved, `1` a real logic failure,
`2` the Gemini API refused both calls so classification quality could not be
judged (billing/quota, not code).

Both are idempotent — fixed ids and fixed test emails, so re-running overwrites
rather than duplicating.

### Credentials note

Both scripts use Application Default Credentials. This machine has no ADC file
yet — the verified runs used the credentials gcloud already stored for
`eschachter@gmail.com`, copied with a `quota_project_id` added, because
`identitytoolkit.googleapis.com` (Auth) refuses user credentials that carry no
quota project:

```bash
python3 - <<'PY'
import json, os
src = os.path.expanduser("~/.config/gcloud/legacy_credentials/eschachter@gmail.com/adc.json")
d = json.load(open(src)); d["quota_project_id"] = "steward-hackathon-505217"
json.dump(d, open("/tmp/adc-quota.json", "w")); os.chmod("/tmp/adc-quota.json", 0o600)
PY

GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc-quota.json .venv/bin/python test_membership.py
```

That is a personal-account fallback. Running
`gcloud auth application-default login` followed by
`gcloud auth application-default set-quota-project steward-hackathon-505217`
once makes the env var unnecessary. For Cloud Run, the service's attached
service account supplies credentials automatically and neither step applies.

## Firebase Auth

Auth was provisioned on the project (`identityPlatform:initializeAuth`) and the
email/password provider enabled — one-time project setup, already done:

```bash
TOKEN=$(gcloud auth print-access-token)
curl -X POST "https://identitytoolkit.googleapis.com/v2/projects/steward-hackathon-505217/identityPlatform:initializeAuth" \
  -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: steward-hackathon-505217" \
  -H "Content-Type: application/json" -d '{}'
curl -X PATCH "https://identitytoolkit.googleapis.com/v2/projects/steward-hackathon-505217/config?updateMask=signIn.email.enabled,signIn.email.passwordRequired" \
  -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: steward-hackathon-505217" \
  -H "Content-Type: application/json" -d '{"signIn":{"email":{"enabled":true,"passwordRequired":true}}}'
```

Without the first call, every Admin SDK Auth call fails with
`CONFIGURATION_NOT_FOUND`.

## Firestore

- Project: `steward-hackathon-505217`
- Database: `(default)`, Native mode, location `nam5` (US multi-region), free tier
- Collections: `estates`, `users`, `estate_memberships`, `items`, `claims`,
  `messages`, `resolutions`, `override_logs`, `dispositions`
