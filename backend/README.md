# Steward — backend

Tier 1 Pydantic models and a Firestore initialization script. No API or agent
logic yet.

| File                | Purpose                                                     |
| ------------------- | ----------------------------------------------------------- |
| `models.py`         | Pydantic models for Estate, User, EstateMembership, Item     |
| `init_firestore.py` | Seeds one document per collection and reads it back          |
| `requirements.txt`  | `firebase-admin`, `pydantic`                                 |

## Running the init script

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Credentials — see note below
gcloud auth application-default login
gcloud auth application-default set-quota-project steward-hackathon-505217

.venv/bin/python init_firestore.py
```

The script is idempotent: seed documents use fixed ids, so re-running overwrites
rather than duplicating.

### Credentials note

`init_firestore.py` uses Application Default Credentials. This machine has no ADC
file yet — the verified run used the credentials gcloud already stored for
`eschachter@gmail.com`:

```bash
GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/legacy_credentials/eschachter@gmail.com/adc.json" \
  .venv/bin/python init_firestore.py
```

That works, but it is a personal-account fallback. Run
`gcloud auth application-default login` once to set up ADC properly and the env
var becomes unnecessary. For Cloud Run, the service's attached service account
supplies credentials automatically and neither step applies.

## Firestore

- Project: `steward-hackathon-505217`
- Database: `(default)`, Native mode, location `nam5` (US multi-region), free tier
- Collections: `estates`, `users`, `estate_memberships`, `items`
