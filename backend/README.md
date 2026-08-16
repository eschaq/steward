# Steward — backend

Tier 1 Pydantic models, Firestore initialization, estate membership (Auth users,
invites, role checks), claims, resolutions, dispositions, the adaptive suggestion
loop, and the Message Center with its two agent behaviors — the last wrapped as
Google ADK tools. All of it sits behind a FastAPI app with Firebase ID token
authentication, which is what Cloud Run serves.

| File                 | Purpose                                                        |
| -------------------- | -------------------------------------------------------------- |
| `models.py`          | Pydantic models for Estate, User, EstateMembership, Message, Claim, Item |
| `firebase_app.py`    | Initializes the Admin SDK once per process; `get_db()`          |
| `membership.py`      | Create Auth user, invite to estate, accept invite, role check   |
| `classify.py`        | Photo → the four `ai_*` Item fields, via Vertex AI              |
| `items.py`           | Writes a classified photo out as an Item document               |
| `claims.py`          | Record a claim; re-derive item status from its claims           |
| `messages.py`        | The feed, the agent User, and the agent's two behaviors         |
| `agent.py`           | ADK tools wrapping the two agent behaviors; the `LlmAgent`       |
| `auth_deps.py`       | Verifies the Firebase ID token; `CallerUid` dependency           |
| `dev_tokens.py`      | Real ID tokens for the test scripts (test accounts only)         |
| `api.py`             | FastAPI app — the routes Cloud Run serves                        |
| `resolutions.py`     | Executor resolves a claimed/contested item; flips to `resolved` |
| `overrides.py`       | OverrideLog + the adaptive suggestion loop                       |
| `dispositions.py`    | Executor's final call: writes the Disposition row + OverrideLog  |
| `photos.py`          | Item photographs in Cloud Storage                                |
| `marketplace.py`     | **Tier 2** — which marketplace to sell on, and why                |
| `mailer.py`          | The invitation email, over Gmail SMTP. Best-effort, never a gate  |
| `init_firestore.py`  | Seeds one document per collection and reads it back             |
| `seed_demo_items.py` | Demo inventory for the dashboard — **not** a test fixture       |
| `test_membership.py` | Script: invite + accept two users, print each role              |
| `test_classify.py`   | Script: classify a real photo and a blank square, store both    |
| `test_claims.py`     | Script: claim one item alone, another twice, check statuses     |
| `test_messages.py`   | Script: both agent behaviors fire once, and only once           |
| `test_resolutions.py`| Script: beneficiary refused, executor resolves, unclaimed refused |
| `test_overrides.py`  | Script: same photo, cold start vs. after the estate has a habit  |
| `test_dispositions.py`| Script: a decision writes both docs; uncertain/unresolved refused |
| `test_recompute.py`  | Script: a stale suggestion catches up; a resolved one is left alone |
| `test_marketplace.py`| Script: channel recommendation, real Gemini; donate refused      |
| `test_api.py`        | Script: both behaviors over HTTP via ADK, byte-identical copy    |
| `test_endpoints.py`  | Script: every endpoint, valid vs unauthorized actor              |
| `requirements.txt`   | `firebase-admin`, `pydantic`, `google-adk`, `google-genai`, …   |

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

## Agent layer (ADK) and the API

`agent.py` wraps the two agent behaviors as ADK `FunctionTool`s and holds them on
a real `LlmAgent`. This is a **structural wrap, not a rewrite** — the copy the
family reads and the Message writing both stay in `messages.py`, and the
no-double-post guarantee still lives in `messages._post_once`. The tools look up
what each behavior needs from Firestore and hand off.

```python
steward_agent            # LlmAgent, model gemini-3.5-flash, holding both tools
await run_behavior_for_item(item_id)
#  {"behavior": "mediate_contested_item", "item_status": "contested",
#   "status": "posted", "item_id": …, "message_id": "agent-mediate__…"}
```

| Item status           | Tool                     |
| --------------------- | ------------------------ |
| `needs_clarification` | `ask_about_unclear_item` |
| `contested`           | `mediate_contested_item` |

### Why the tools are invoked directly, not through a model turn

Both behaviors fire on a **state transition the backend already detects** — an
item landing in `needs_clarification`, or flipping to `contested`. There is no
decision for a model to make about which one applies, and letting one choose
would put the family's message content at the mercy of a sampling temperature.

So `run_behavior_for_item` dispatches on status and invokes the tool through
ADK's own `run_async` contract — argument validation, tool declarations, and
result shape all go through the framework, and a `{"error": …}` return is raised
rather than read as success. `steward_agent` is a real `LlmAgent` holding these
tools, ready for the model-driven paths (a "what should we do with the garage?"
conversation) that come later.

### Classification is not wrapped as a tool

Three reasons, in order of weight:

1. **It isn't an action an agent decides to take.** Classification produces the
   input the agent reasons *about*. Fronting it as a tool means an LLM turn whose
   only job is to decide to make another LLM call.
2. **It would disrupt a verified path.** `classify.py` pins generation to a
   `response_schema` and parses with `raw_decode` to tolerate a known
   `gemini-3.5-flash` quirk (an occasional stray `}`). Routing it through an
   `LlmAgent` replaces that with ADK's own response handling and loses the
   tolerance.
3. **The right change was a migration, not a wrap.** `google-adk` brought in
   `google-genai`, and `classify.py` has since moved onto it and onto Vertex AI —
   a transport change, done separately, rather than folding classification into
   an agent turn.

### The agent route

`POST /items/{item_id}/agent-message` — see the API section below. 409 if the
item is in a state no behavior attaches to; a 200 that quietly did nothing would
be the failure mode the RDD rules out. Calling twice is safe — the second call
reports `already_asked` / `already_mediated`.

Verified run against real Firestore (`test_api.py`, driven with FastAPI's
`TestClient` — no live server):

```
(a) needs_clarification -> POST writes the clarifying question
    text == messages.clarifying_question_text(same inputs)   [exact match]
    second POST -> already_asked, still 1 message, created_at untouched
(b) contested -> POST writes the mediating suggestion
    text == messages.mediation_text(same claimants, same order)  [exact match]
    second POST -> already_mediated, still 1 message, created_at untouched
(c) unclaimed item -> 409, nothing written;  unknown item -> 404
```

The equality assertions compare against `messages.py`'s own copy functions, so
"the ADK path writes what the direct path wrote" is checked rather than assumed.

## The API

```bash
.venv/bin/uvicorn api:app --reload      # local
```

| Route                                | Who                        | Wraps                          |
| ------------------------------------ | -------------------------- | ------------------------------ |
| `GET  /healthz`                       | anyone (no token)          | —                              |
| `POST /estates/{id}/invite`           | executor                   | `invite_to_estate`             |
| `POST /estates/{id}/accept`           | the invitee themselves     | `accept_invite`                |
| `GET  /estates/{id}/items`            | any accepted member        | `list_items_for_estate`        |
| `POST /estates/{id}/items`            | executor                   | `store_item_photo` + `classify_bytes` + `create_item_from_classification` |
| `GET  /estates/{id}/members`          | any accepted member        | `list_memberships` + `users`   |
| `GET  /estates/{id}/review`           | any accepted member        | composes items + claims + resolutions + dispositions |
| `GET  /items/{id}`                    | any accepted member        | `get_item`                     |
| `GET  /items/{id}/messages`           | any accepted member        | `get_messages_for_item`        |
| `GET  /items/{id}/claims`             | any accepted member        | `get_claims_for_item`          |
| `GET  /estates/{id}/me`               | any signed-in caller       | `get_membership`               |
| `GET  /estates/{id}/messages`         | any accepted member        | `get_messages_for_estate`      |
| `GET  /items/{id}/resolution`         | any accepted member        | `get_resolution`               |
| `GET  /items/{id}/disposition`        | any accepted member        | `get_disposition` + its listing |
| `POST /estates/{id}/messages`         | any accepted member        | `post_message`                 |
| `POST /items/{id}/claim`              | any accepted member        | `record_claim`                 |
| `DELETE /items/{id}/claim`            | the claimant themselves    | `withdraw_claim`               |
| `POST /items/{id}/resolve`            | executor                   | `resolve_item`                 |
| `POST /items/{id}/disposition`        | executor                   | `record_disposition_decision`  |
| `POST /items/{id}/disposition/advance`| executor                   | `advance_disposition`          |
| `POST /items/{id}/photo`              | executor                   | `store_item_photo`             |
| `POST /items/{id}/marketplace-listing`| executor                   | `recommend_channel`            |
| `POST /items/{id}/remove`             | executor                   | `remove_item` (soft delete)    |
| `POST /items/{id}/agent-message`      | any accepted member        | `run_behavior_for_item`        |

### Taking your name back off

`DELETE /items/{id}/claim` withdraws the caller's own claim. **DELETE, and it
means it** — unlike `/items/{id}/remove`, the Claim documents genuinely go away.
There is no withdrawn flag on Claim in the data model, and inventing one would
be a schema change to record an absence the collection already expresses by not
containing the row.

**The claimant's own call, not the executor's.** A caller can only ever withdraw
their own claim because the uid comes from their verified token and never from
the path or the body — "not someone else's" is structural here, not a check that
could be forgotten.

**It removes every claim that person has on the item, not one row.** Repeat
claims are deliberately allowed (a second is usually a revised comment), so
someone can hold more than one; they are withdrawing their interest, and leaving
a stray row would leave their name on the item.

Status comes back through `recompute_item_status` — the same function
`record_claim` uses, so the way down is the way up in reverse with no second
copy of the 0/1/2+ rule. Dropping a contested item to one claimant lands on
`claimed` because `status_for_claimant_count` counts distinct claimants and does
not care which direction it is moving. Mediation posts only on the transition
*into* contested, so coming back down says nothing.

404 for no such item, and for having no claim to take back — asking to withdraw
something you never put down is a mistake worth naming.

**The mediation message stays.** Messages are append-only, and the agent did say
that at the time — deleting it would rewrite history and orphan any replies. But
"leave it" alone was not the whole answer: the item detail view already gates the
prominent "A way through" treatment on `item.status === 'contested'`, so once the
item settles back down the mediation demotes itself to an ordinary thread entry.
The record is kept; the live prompt is not. Verified: after a withdrawal the
thread still holds the message and nothing is highlighted.

### Getting it out of the house

`POST /items/{id}/disposition/advance` moves a Disposition one step:
`pending → in_progress → completed`. Executor only. Nested under the disposition
rather than a top-level verb, because what moves is the Disposition — the item's
status changing is a consequence.

**One step per call.** Each step corresponds to something that happened in the
world (the charity shop has it; the charity shop has taken it), so skipping to
the end would record an event nobody witnessed.

**`in_progress` sets the item to `routed`** — the only place anything sets it.
Nothing else in the codebase reads `routed`: the three status gates are
allow-lists that exclude it, so a routed item is already out of claiming,
resolving and suggestion recompute.

**Completion gets no new Item status, and that is a reading of the data model
doc rather than an omission.** Disposition is given its own `status` and
`completed_at` precisely so the fulfilment lifecycle lives there, and the doc's
own note says every tier's detail "lives in tables that reference Disposition,
never in Item/Claim/Comment/Resolution themselves". An eighth Item status
meaning "gone" would push disposition detail back up into Item — the exact thing
the seam exists to prevent — and would create a second source of truth that
could disagree with `completed_at`. Item.status answers *where did this land in
the claim flow*; Disposition answers *and has it actually gone yet*.

Errors follow the house pattern: 403 `MembershipError` for a non-executor, 409
`DispositionError` for no disposition yet or one already completed, 404 for no
such item (checked before anything else — a missing item is not a state
conflict).

`test_dispositions.clear_decision` now also puts a `routed` item back to
`resolved`. Dropping the Disposition without undoing its effect left a routed
item with nothing routing it, and the next decision was refused because only a
resolved item is eligible — which `test_marketplace` caught.

### Taking an item off the list

`POST /items/{id}/remove` is a **soft delete**: `status` moves to `removed` and
nothing else changes. The document stays, its claims and messages stay attached,
and the item stays readable at its own URL — deleting it would orphan everything
pointing at it and leave the family a gap they cannot ask about. Visible state
beats silent erasure.

**POST, not DELETE.** DELETE promises the resource goes away, and it does not.
Naming the action honestly beats borrowing a verb whose meaning is wrong here,
and it matches the other action endpoints (`/claim`, `/resolve`,
`/disposition`).

**Idempotent, not an error.** Removing something already removed asks for a
state it is already in, so there is nothing to refuse — the second call returns
the same item and writes nothing. That matches `accept_invite`, and differs from
the 409s in `dispositions.py` and `marketplace.py`, which refuse a *different*
end state and so are real caller mistakes.

`removed` is the data model doc's seventh status, added 2026-08-15. It needed no
new checks anywhere: `CLAIMABLE_STATUSES`, `RESOLVABLE_STATUSES` and
`SUGGESTION_ELIGIBLE_STATUSES` are allow-lists, so a removed item falls out of
claiming, resolving and suggestion recompute by construction.

`list_items_for_estate(estate_id, include_removed=False)` does the filtering, so
the dashboard **and** the review table inherit it from one place. Filtering
happens in Python rather than the query, so the `estate_id` equality filter stays
covered by Firestore's automatic index — a second `where` would want a composite
one.

**firestore.rules deliberately does not allow `removed`** in its client-writable
status list. That rule can only check membership, and removal is executor-only,
so it has to go through this endpoint where `require_role` can see the role.

### Cataloguing a belonging

`POST /estates/{id}/items` is the entry point of the whole thing: one photograph
in, one Item out. Executor only, the same gate as the append-photo endpoint —
cataloguing is their job.

**It adds no judgement of its own**, which is the point. The photo goes to Cloud
Storage through `store_item_photo`, the bytes go to `classify_bytes`, and
`create_item_from_classification` does everything else exactly as the seed
script does: the 0.6 confidence threshold picks the status, the OverrideLog
weights the suggestion, and an item landing in `needs_clarification` gets the
agent's clarifying question posted to the family's feed. A photo uploaded here
behaves identically to one classified from disk because it runs the same code.

The item's document id is **reserved before the upload** (`reserve_item_id`), so
the photograph is filed under the item it belongs to rather than needing a
second key. Order of operations matters: an unusable file is rejected at 422
before any Gemini call and before any document is written, so it leaves nothing
behind.

**`photo_urls` holds only the stored URL.** The seed and test paths also record
the local file they read, which is why `photo_urls[0]` is not always displayable
elsewhere; nothing created through this endpoint has that problem.

A classification that *fails* does not fail the request — it comes back at
confidence 0.0 and the item lands in `needs_clarification` with an honest note,
which is what that status is for.

`classify.py` gained `classify_bytes(data, mime_type)` as the single
implementation; `classify_image(path)` now reads the file and calls it. No temp
file, and no second copy of the prompt, schema, threshold or failure handling to
drift apart.

### The invitation email

`POST /estates/{id}/invite` generates a real Firebase password-reset link with
the Admin SDK and emails it, over Gmail SMTP with an app password from
`backend/.env` (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` — gitignored, and read by
a twelve-line loader in `mailer.py` rather than reinstating `python-dotenv`,
which this project dropped when classification moved to Vertex AI).

**The email is a courtesy on top of the membership, never a gate in front of
it.** Everything after `invite_to_estate` is best-effort: no credentials, a
rejected SMTP login, a dropped connection, or a link that could not be
generated all come back as `invite_email_sent: false` plus a plain
`invite_email_note`, and the invite still succeeds with a 200. `send_invite_email`
has no exception path at all — a mail server having a bad day must not stop a
family adding someone to their own estate. Verified both ways:

```
credentials unset  -> sent=False  "No email was sent — this copy of Steward has
                                   no mail account set up. You'll need to pass
                                   the word along yourself."
wrong app password -> sent=False  "The invite is recorded, but the email didn't
                                   go out (SMTPAuthenticationError). Worth
                                   telling them yourself."
```

`STEWARD_APP_URL` becomes the link's `continueUrl`, so the invitee is returned
to Steward once the password is set. That domain has to be on the project's
authorized-domains list — `localhost` was added for local work. If it isn't,
`_invite_link` logs it and falls back to a link with no continue URL rather than
giving up: a link that sets a password but doesn't offer a way onward is far
better than no link.

The subject is "You've been asked to {estate name}" and the body names who
asked. No "You have been invited to join a workspace", nothing about activating
an account, and a closing line that says there is no hurry.

### What an invited person can actually do

Worth being exact about, because Firebase's own behaviour is what shapes the
flow. Probed against real Firebase Auth:

```
executor invites ruth@example.com (create_account: true)
  -> auth.create_user(email=...)      providers: (none)   no password
  -> signInWithPassword               400 INVALID_LOGIN_CREDENTIALS
  -> self sign-up, same address       400 EMAIL_EXISTS
  -> generate_password_reset_link     OK
  -> sendOobCode PASSWORD_RESET       200, email sent by Firebase
  -> resetPassword with that oobCode  200, password set
  -> signInWithPassword               200, signed in
```

So: **the invite claims the address**, which means the invitee cannot register
it themselves, and it leaves them an account with no password and no way in
until someone tells them to use the reset flow. Steward sends **no invitation
email** — that would need an email service and is not built. Firebase does send
the password-reset email itself, with no SMTP configuration, which is what makes
the rest of the path real.

So the invite claims the address — the invitee cannot register it themselves —
and leaves them an account with no password. `mailer.py` closes that: the link
they need is now emailed to them the moment they are invited. The sign-in
screen's "Forgot your password?" control remains as the way back in if the
email never arrives or the link goes stale.

Verified end to end against a real inbox, through the real endpoint, using the
exact link that was sent:

```
POST /invite  ->  200, invite_email_sent: true
  subject      "You've been asked to Seed Estate"
  link mode    resetPassword     continueUrl  http://localhost:5173
1. sign in before the link  -> 400 INVALID_LOGIN_CREDENTIALS
2. follow the emailed link  -> 200 password set
3. sign in after the link   -> 200 signed in
4. membership               -> pending; <Arrival> accepts it and runs the welcome
```

### Authentication

`auth_deps.current_uid` verifies the `Authorization: Bearer <Firebase ID token>`
header with the Admin SDK and returns the uid. Because the Firebase Auth uid *is*
the `User.id`, that uid goes straight into `require_role` with no lookup.

Handlers annotate `uid: CallerUid` — there is no user id in any request body, so
a caller can only ever act as themselves. `verify_id_token` runs with
`clock_skew_seconds=30`: a second of drift between this host and Google's clock
is ordinary and shouldn't read as a forged token.

The claims list is readable by any accepted member, not just the executor: a
family cannot talk a contested piece through if only one person can see who
wants it. It returns both `count` (documents, duplicates included) and
`claimant_count` (distinct people) — the second is what drives the item's status.

`GET /estates/{id}/review` exists for one reason: the executor's review table
needs an item's claim count, its resolution and where it is headed alongside it,
and asking per item turned 38 items into 114 round trips. It composes reads that
already exist — no new entity, no new collection. Claims are fetched by chunked
`in` query (30 ids at a time, Firestore's limit); resolutions, dispositions and
their marketplace listings by their deterministic document ids through
`get_all`. The whole table is five reads rather than three per row.

The disposition on a review row is the same `DispositionDetail` the per-item
endpoint returns, built by the same `_as_disposition_detail` mapper — the review
table and the item page cannot drift into describing one decision two different
ways. `_dispositions_for_items` is the batched form of that read and nothing
else; the single-item endpoint still reads one document.

`ItemSummary` carries `decided_channel` for the same reason, filled from that
same batched read on the list endpoint and one extra document read on
`GET /items/{id}`. It is deliberately *not* `suggested_disposition`: one is
Steward's reading of a photograph, the other is what the executor decided, and
a dashboard card that conflates them would be lying about which it is showing.
The channel alone — no platform, no reason — because a card that needs those has
an item page one click away.

`GET /estates/{id}/members` is everyone invited here, accepted or still
pending, ordered by when they were asked. Readable by any accepted member — who
else is in this with you is not privileged information inside a family — while
inviting stays executor-only. Names and emails are resolved from the `users`
mirror in one batched `get_all`, because a membership row holds only a uid and
the frontend cannot read that collection.

`POST /estates/{id}/accept` returns `first_accept` — true only for the call
that actually turned a pending invite into a membership. It is read before the
write (`get_membership`, then `accept_invite`) rather than stored as a flag:
EstateMembership's fields are fixed by the data model doc, and "have they been
welcomed yet" was already answerable from whether `accepted_at` was still null.
Accepting is idempotent, so every later call reports `false`. That is what the
frontend's one-time welcome hangs on.

`GET /estates/{id}/me` also carries `estate_name` (so a screen can say "Seed
Estate" rather than print `seed-estate-001` at a grieving family — null if the
record has no name) and `invite_pending`, which is what lets the client offer
acceptance instead of a bare "you have no role here". It is
deliberately **not** a 403 for a non-member — "you have no role here" is a fact
the UI needs in order to say so plainly. It governs what is *offered*, never
what is *allowed*; every write still goes through `require_role`.

`GET /items/{id}/resolution` returns `null` rather than 404 when nothing has
been decided: no decision yet is the ordinary state of most items, not a missing
resource. `GET /items/{id}/disposition` does the same, and nests the
MarketplaceListing inside the disposition when there is one — the only moment
anything wants a listing is immediately after reading its disposition, so a
second round trip would buy nothing. Both are readable by any accepted member:
where a piece is headed is family news, even though only the executor decides
it.

`POST /items/{id}/marketplace-listing` is executor-only and runs
`recommend_channel`, which is a real Gemini call. It 409s on a donate or discard
disposition, and on an item with no disposition at all — see the Tier 2 section
below.

`GET /estates/{id}/messages` is the whole feed — item-specific and general
interleaved by time, because the data model keeps them in one collection with a
nullable `item_id`. The per-item thread is that same data filtered, not a second
feed. Both go through one `_message_responses` mapper, so the agent/human
distinction and the name lookup are decided once.

On `POST`, the author is the caller — there is no `user_id` in the body, so
nobody can post as someone else or as Steward. An `item_id` in the body is
checked to belong to *this* estate; without that a member could hang a message
off an item they cannot otherwise see.

The message thread and the claims list both resolve display names server-side. `firestore.rules`
lets a caller read their own `users` document and nothing else, so a feed
rendered client-side would show bare uids — resolved here rather than by
widening that rule.

### Authorization is not in the route layer

Routes do three things: establish who is calling, hand off, and translate
exceptions into status codes. The rules stay in `require_role` (membership.py)
and in the state gates inside resolutions.py and dispositions.py — already
verified against real Firestore. A route that re-decided those questions would be
a second copy free to drift from the first.

| Status | Meaning                                        | Source                    |
| ------ | ---------------------------------------------- | ------------------------- |
| 401    | no token, or one that doesn't verify           | `auth_deps`               |
| 403    | authenticated, but not allowed                 | `MembershipError`         |
| 404    | no such item, or no invite to accept           | route-level lookup        |
| 409    | allowed, but not in a state for it             | `Claim`/`Resolution`/`DispositionError` |

`POST /estates/{id}/accept` deliberately does **not** call `require_role`: a
pending invitee has no role yet — that is precisely what they are accepting. They
can only accept their own invite, since the uid comes from the verified token.
`firestore.rules` lets only the executor write a membership row, so this endpoint
is the path an invitee has to take.

Verified run against real Firestore (`test_endpoints.py`), with **real ID
tokens** minted by signing test users in against Identity Toolkit — nothing about
auth is stubbed:

```
no token / garbage token / wrong scheme      -> 401
beneficiary or stranger invites              -> 403, no membership written
executor invites                             -> 200, membership pending
stranger accepts                             -> 404, nothing written
invitee accepts their own                    -> 200, accepted_at set
stranger lists items                         -> 403
stranger claims                              -> 403, no claim, item untouched
beneficiary resolves                         -> 403, no resolution, item untouched
executor resolves an unclaimed item          -> 409, nothing written
beneficiary decides a disposition            -> 403, neither document written
executor decides on an unresolved item       -> 409, neither document written
'uncertain' as a decision                    -> 409, nothing written
```

Each refusal asserts the collections are **untouched**, not just that a status
code came back — a 403 that had already written its document would pass a
status-only test and still be a hole.

### Test tokens

`dev_tokens.py` mints real ID tokens by signing a test user in with
email/password. `auth.create_custom_token` would be tidier, but it needs a
service account to sign with and this machine authenticates as a user.

It sets the account's password to do that, so it **refuses any address outside
`@example.com`**. The browser API key comes from `STEWARD_WEB_API_KEY` or, absent
that, from `gcloud services api-keys` — it is not committed.

## Item photographs

`photos.py` stores an uploaded photograph in Cloud Storage and `items.add_photo_url`
appends the resulting URL to `Item.photo_urls`. Executor only — cataloguing is
their job, and a beneficiary adding photographs to someone else's belongings is a
different feature with different questions behind it.

Bucket: **`steward-hackathon-505217-item-photos`**, us-central1, uniform
bucket-level access, `allUsers` granted `roles/storage.objectViewer`. The
`.firebasestorage.app` default bucket does not exist and cannot be created with
`gcloud` — Google owns that domain — so this is an ordinary project bucket.

### Public-read objects, not signed URLs

Chosen deliberately:

- **Signed URLs need something to sign with.** This project authenticates as a
  user (ADC, no service-account key), so `generate_signed_url` has no private key
  and would need an IAM signBlob round trip against a service account to
  impersonate — the same wall `auth.create_custom_token` hit in `dev_tokens.py`.
- **A signed URL expires.** `photo_urls` is a *stored* field that the dashboard
  and the review table read directly. A URL that dies in an hour would mean
  minting fresh ones on every read — a different shape from what the data model
  describes.

Each object path carries a `uuid4` (`items/{item_id}/{uuid}.jpg`), so a URL
cannot be guessed from an item id. That is the same practical property a Firebase
download token gives.

⚠️ **It is still readable by anyone holding the link**, and these are a grieving
family's belongings. Fine for a demo on a private project; not the right answer
for real estates. Before that, either proxy reads through the API behind
`require_role`, or attach a service account and switch to short-lived signed URLs
generated per read.

Uploads are capped at 12MB and limited to jpeg/png/webp/heic. Anything else comes
back as a 422 saying what was wrong, not a silent drop.

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

## Marketplace channel (Tier 2)

The first piece of Tier 2, built only because it was explicitly asked for —
CLAUDE.md gates this tier behind an explicit request.

`marketplace.recommend_channel(item_id)` reads the item's Disposition, asks
Gemini where to sell it, what to ask for it and how to describe it, and writes a
`MarketplaceListing` in `draft`. It attaches at the Disposition seam exactly as
the data model describes: nothing in Tier 1 changed to accommodate it.

**One call for all four fields**, not a channel call followed by a pricing call.
They condition on each other — the same sideboard is worded and priced one way
as a local Facebook collection and another way as an eBay listing to a
collector, and a second call would be free to disagree with the first. Asking
once also halves the wait the executor sits through, and no caller wants the
platform without the rest. `listing_url` stays null: posting it somewhere is a
human act, not a generated one.

- **Only `sell_marketplace` dispositions are eligible.** A donate or discard
  decision raises `MarketplaceError`, and so does an item with no disposition at
  all. Both are caller mistakes, and skipping silently would hide them.
- **The Vertex client is classify.py's.** `vertex_client()` and `model_name()`
  were made public for this; there is one client per process, not one per module.
- **Generation is schema-constrained** so `platform` can only be one of the five
  the data model allows — the model cannot invent a sixth — and
  `suggested_price` comes back as a number rather than "about $40".
- **The price is a starting point, and the prompt says so.** A defensible
  ballpark the executor will adjust, rounded to something a person would type.
  `_price()` rejects negatives, NaN and anything over $1,000,000 as a parse
  artefact rather than storing it.
- **The draft copy has to name the damage.** The prompt puts wear, breakage and
  missing pieces in the description rather than leaving them for the buyer to
  find, and forbids inventing any detail not in the condition notes — so a thin
  set of notes produces a short description, not a padded one.
- **Failure degrades honestly.** A transport error, a quota rejection or an
  unparseable reply all come back as `platform=other` with "Couldn't work out the
  best place for this one — worth having a look yourself", and the other three
  fields null. Same shape as classify.py: an "I don't know" that is visible in
  the data, never a plausible guess.
- **A partial reply keeps the part that worked.** A response good enough to name
  a platform but not to price the thing nulls the price alone rather than being
  thrown away whole — so the executor still gets the channel and its reason.
- One listing per disposition, via a deterministic id (`listing__{disposition_id}`),
  so re-running replaces the draft rather than stacking them.

Verified against real Firestore and real Gemini (`test_marketplace.py`):

```
demo-canteen-cutlery silverware -> ebay, $45
  reason: "An antique Sheffield plate cutlery set is best suited for eBay,
           where collectors and vintage buyers specifically search for
           historical tableware despite some wear."
  title : "Vintage Unmarked Sheffield Plate Cutlery Canteen, Service for Six"
  body  : "An unmarked Sheffield plate canteen of cutlery for six, presented in
           a baize-lined oak box. Please note that the silver plating has worn
           to the copper on the backs of the spoons, two teaspoons are missing,
           and the box lock does not catch."

demo-brass-lamp      table lamp -> fb_marketplace, $35
  reason: "This brass table lamp is awkward and fragile to post with its shade,
           so listing on Facebook Marketplace allows for an easy local
           collection."
  title : "Vintage 1970s brass column table lamp"
  body  : "A brass column table lamp from the 1970s. It has been rewired at some
           point with modern, correctly earthed flex. The pleated shade is
           water-stained along one side and is slightly out of round."

donate disposition   -> MarketplaceError, nothing written
no disposition yet   -> MarketplaceError, nothing written
```

Every flaw in the condition notes made it into the description — worn plating,
two missing teaspoons, the lock that doesn't catch, the water-stained shade. The
two items also reached different platforms for different reasons, which is what
tells you the model is reading the item rather than the category.

The test asserts each reason draws at least two distinctive words from that
item's own record, that the two reasons differ in substance, that the price is a
number in a sane range, that the title fits a title field and isn't SHOUTING,
that the description carries at least two of the item's own condition words, and
that none of it contains reseller-hustle language ("maximise", "act fast", "top
dollar", "rare find", "must see" …).

An earlier version of that check demanded the literal category word and failed
the cutlery reason, which says "Sheffield plate cutlery set in its oak box" —
more specific than the check allowed for. Testing for a keyword echo is not the
same as testing for specificity.

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

`classify.py` calls **Vertex AI** through the `google-genai` SDK on Application
Default Credentials — no API key, no `.env`. Model is `gemini-3.5-flash`;
override with `GEMINI_MODEL`.

**Location is `global`, not a named region.** Vertex serves `gemini-3.5-flash`
from `global` only: asking `us-central1` for it returns 404 even though the
project has Vertex access there (`gemini-2.5-flash` answers from `us-central1`
fine, which is how we know it's the model and not the project). Override with
`VERTEX_LOCATION` if a future model is region-pinned.

The client is cached module-level on purpose. It owns an httpx connection pool
and closes it when collected, so a per-call client can be finalized out from
under its own in-flight request — `RuntimeError: Cannot send a request, as the
client has been closed`. One per process, like the Firebase app.

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

Verified run on Vertex — real photo, real API, real Firestore. Identical results
to the pre-migration run, which is the point:

```
sample_item.png              armchair, "Louis XV style", confidence 0.98 -> unclaimed
generated_blank_square.png   unknown, confidence 0.0 -> needs_clarification
```

### Credentials

Application Default Credentials, the same ones Firestore and Auth use — see the
credentials note under "Running the scripts". On Cloud Run the attached service
account supplies them automatically. **No key material anywhere.**

The AI Studio API key path is gone: `.env`/`GEMINI_API_KEY` are no longer read by
anything, and with them went the free tier's 20-requests-per-day cap that used to
block `test_classify`, `test_overrides`, and `test_recompute` partway through a
day. Blaze billing is active on the project.

### SDK

`google-genai`, which `google-adk` already required — the migration added no
dependency. `google-generativeai` (deprecated, and its protobuf pin conflicted
with `google-cloud-firestore`'s) and `python-dotenv` were both uninstalled, and
the full suite was re-run afterwards to prove nothing still reached for them.

The migration was a transport change only. The `response_schema` constraint and
the `raw_decode` tolerance for `gemini-3.5-flash`'s occasional stray `}` are
unchanged, as are the prompt, the confidence threshold, and the degradation path.

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
.venv/bin/python test_api.py
.venv/bin/python test_endpoints.py
```

### Demo data

```bash
.venv/bin/python seed_demo_items.py
```

Adds 14 varied belongings to `seed-estate-001` so the dashboard looks like an
estate rather than the near-identical fixtures the suites leave behind. Nothing
in the test suites touches these, and this touches nothing they create.

**Hand-seeded, not agent-classified.** Every `ai_*` value is written by hand and
plausible; none of it went through `classify.py`. Provenance lives in the
document id, because Item's shape is fixed by the data model doc and this script
does not get to add a `source` field:

| Prefix | Origin |
| ------ | ------ |
| `demo-` | `seed_demo_items.py` — hand-written |
| `test-` | backend verification suites |
| anything else | the real pipeline, `classify.py` → `items.py` |

It writes Claims behind every `claimed`/`contested` item and Resolutions behind
every `resolved`/`routed` one, so no status is a label with nothing under it. It
deliberately writes **no Disposition or OverrideLog rows**: those would change
what the agent suggests for future items in those categories, and seed data
should not quietly retrain the adaptive loop.

**Re-running preserves `photo_urls`.** Every other field is overwritten back to
its seeded value — that is the point of re-seeding — but photographs are uploaded
by a person through the app, not seeded here. The script reads any existing
`photo_urls` off the document and carries them onto the record before writing,
and prints how many it kept. A fixture script should not destroy someone's work.

All ten pass against Vertex AI and real Firestore. `test_classify`,
`test_overrides`, and `test_recompute` make live Gemini calls; the other six make
none.

The AI Studio free tier's 20-requests-per-day cap no longer applies — it used to
block those three partway through a day, and they still exit `2` (BLOCKED, quota
not logic) rather than `1` if a quota wall ever reappears.

`test_classify.py` exit codes: `0` both cases behaved, `1` a real logic failure,
`2` the Gemini API refused both calls so classification quality could not be
judged (billing/quota, not code).

Both are idempotent — fixed ids and fixed test emails, so re-running overwrites
rather than duplicating.

### Java 21, for the Security Rules emulator

Not needed for anything in this directory — the backend suites run against real
Firestore. It is needed for `rules-tests/` at the repo root, which runs
`firebase emulators:exec`, and the emulator is a JVM process.

**firebase-tools 15 refuses Java below 21**, and Debian 12's
`default-jre-headless` is 17, with no `openjdk-21` package in this apt config.
So a Temurin 21 runtime lives at:

```
/opt/java/jdk-21.0.12+8-jre     symlinked to /usr/local/bin/java
```

⚠️ **That is outside the repo and is not reproducible from a checkout.** If this
Chromebook container is ever wiped or rebuilt, the emulator tests will fail with
*"firebase-tools no longer supports Java version before 21"* until it is put
back:

```bash
curl -sL -o /tmp/jre21.tar.gz \
  "https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jre/hotspot/normal/eclipse"
sudo mkdir -p /opt/java && sudo tar xzf /tmp/jre21.tar.gz -C /opt/java
sudo ln -sf /opt/java/jdk-21.0.12+8-jre/bin/java /usr/local/bin/java
java -version    # expect 21.x
```

Nothing else in the project depends on a JVM.

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
