# Steward — backend

Tier 1 Pydantic models, Firestore initialization, and estate membership
(Auth users, invites, role checks). No HTTP API or agent logic yet.

| File                 | Purpose                                                      |
| -------------------- | ------------------------------------------------------------ |
| `models.py`          | Pydantic models for Estate, User, EstateMembership, Item      |
| `firebase_app.py`    | Initializes the Admin SDK once per process; `get_db()`        |
| `membership.py`      | Create Auth user, invite to estate, accept invite, role check |
| `classify.py`        | Photo → the four `ai_*` Item fields, via the Gemini API       |
| `items.py`           | Writes a classified photo out as an Item document             |
| `init_firestore.py`  | Seeds one document per collection and reads it back           |
| `test_membership.py` | Script: invite + accept two users, print each role            |
| `test_classify.py`   | Script: classify a real photo and a blank square, store both  |
| `requirements.txt`   | `firebase-admin`, `pydantic`, `google-generativeai`, …        |

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
- **`suggested_disposition` is left `uncertain`.** Per the data model it is meant
  to be weighted by the estate's OverrideLog history, and that loop isn't built
  yet. A one-shot guess here is the thing the RDD explicitly rejects.
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
- Collections: `estates`, `users`, `estate_memberships`, `items`
