# Steward — backend

Tier 1 Pydantic models, Firestore initialization, and estate membership
(Auth users, invites, role checks). No HTTP API or agent logic yet.

| File                 | Purpose                                                      |
| -------------------- | ------------------------------------------------------------ |
| `models.py`          | Pydantic models for Estate, User, EstateMembership, Item      |
| `firebase_app.py`    | Initializes the Admin SDK once per process; `get_db()`        |
| `membership.py`      | Create Auth user, invite to estate, accept invite, role check |
| `init_firestore.py`  | Seeds one document per collection and reads it back           |
| `test_membership.py` | Script: invite + accept two users, print each role            |
| `requirements.txt`   | `firebase-admin`, `pydantic`                                  |

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

## Running the scripts

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Credentials — see note below
gcloud auth application-default login
gcloud auth application-default set-quota-project steward-hackathon-505217

.venv/bin/python init_firestore.py
.venv/bin/python test_membership.py
```

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
