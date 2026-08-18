# Steward — Functional Specification (as built)

**Status:** Tier 1 complete, Tier 2 complete.
**Generated:** 2026-08-16, from the code rather than from the planning docs.
**Supersedes:** the 2026-08-15 revision of this file.

> **This is a dated snapshot, and it has since fallen behind.** It was written
> when nothing was deployed. Since 2026-08-16: both Cloud Run services and the
> Security Rules went to production; the Review screen became three subtabs with
> their own URLs; a per-person "how things have landed" view and a third agent
> behaviour (noticing a shared memory) were added; and one account can now hold
> several estates, switch between them, and remove one that was never used.
> Regenerate before using this for anything that depends on completeness.
**Purpose:** competitive research and enhancement discovery. This describes what
the software *actually does today*, including the parts that are stubbed,
degraded, or deliberately absent.

> Where this document and `docs/estate-agent-RDD.md` disagree, this document is
> right about behaviour and the RDD is right about intent. The RDD is a planning
> artefact from 2026-08-10; a great deal has been built, cut, or changed since.

**What changed since the 2026-08-15 revision** — four loops landed, and three of
them closed gaps this document previously listed as open:

| | |
| --- | --- |
| **Item creation from a photo** | `POST /estates/{id}/items` — the demo arc's entry point now exists as a live flow |
| **Soft delete** | `POST /items/{id}/remove`, and a seventh `ItemStatus` |
| **Fulfilment** | `POST /items/{id}/disposition/advance` — `Disposition.status` moves through all three values and `Item.ROUTED` is finally set |
| **Claim withdrawal** | `DELETE /items/{id}/claim` |

Four real bugs surfaced — two from these loops, two from manual UAT on
2026-08-16 — and are recorded in §11.4, because every one of them was invisible
until something exercised it.

---

## 1. What it is

Steward is a **multi-user agent for estate belongings disposition**. A family
photographs the contents of a house; Steward identifies each object, the family
says what they want, Steward mediates when two people want the same thing, and
the executor records where everything ends up — and, now, that it actually went.

### 1.1 Target user

> The executor of a mid-size family estate — typically an adult child — managing
> 2–5 beneficiary siblings who each have emotional claims on overlapping
> household items, with no professional estate-sale company involved.

The three constraints that matter competitively: **DIY** (no estate-sale company
already engaged), **multi-party** (the hard problem is between people, not
between a person and a spreadsheet), and **emotionally loaded** (the product's
job is partly to keep a family talking).

### 1.2 Positioning, expressed as product constraints

The brand is enforced in code, not just in copy guidelines:

| Constraint | Consequence |
| --- | --- |
| No urgency, countdowns, gamification | No deadlines, no streaks, no "3 items left!" |
| Counts are a ledger, not a score | No progress bars, no percent-complete, no targets |
| Status colours desaturated, never alarm-driven | "Contested" reads as *Needs a talk*, not a red alert |
| No stock imagery | Photo slots take the family's own photo or a tonal wash |
| No shadows | Depth is tonal layering and 1px hairlines |
| Agent suggests, never decides | Every terminal decision requires an executor action |
| Visible state over silent erasure | Soft delete, append-only messages, honest failure notes |

Plain-language status vocabulary, a deliberate differentiator:

| Internal | Shown to users |
| --- | --- |
| `unclaimed` | Unspoken for |
| `claimed` | Spoken for |
| `contested` | **Needs a talk** |
| `resolved` | Settled |
| `routed` | On its way |
| `needs_clarification` | Needs a look |
| `removed` | Taken off the list |

---

## 2. Architecture

```
┌─────────────────────┐         ┌──────────────────────┐
│  Frontend (Vite)    │  HTTPS  │  Backend (FastAPI)   │
│  React 19 + TS      │ ──────► │  Python 3.11         │
│  Firebase Web SDK   │  Bearer │  uvicorn             │
│  (auth only)        │  ID tok │                      │
└─────────────────────┘         └──────────┬───────────┘
        │                                   │
        │ Firebase Auth                     ├──► Firestore (10 collections)
        └──────────────────────────────────►├──► Cloud Storage (item photos)
                                            ├──► Vertex AI  (gemini-3.5-flash)
                                            ├──► Firebase Auth Admin SDK
                                            └──► Gmail SMTP (invitations)
```

**Two Cloud Run services, split deliberately.** The frontend never touches
Firestore or Storage directly — only the backend API. This is the trust boundary
the split exists to enforce, and what makes the Firestore Security Rules a
second line of defence rather than the only one.

### 2.1 Stack

| Layer | Choice | Notes |
| --- | --- | --- |
| LLM | **Gemini 3.5 Flash** via **Vertex AI** | `google-genai` SDK on ADC. No API keys. Served from `global`, not a named region. |
| Agent orchestration | **Google ADK 2.6.3** | `LlmAgent` + two `FunctionTool`s |
| API | FastAPI 0.141 + uvicorn 0.52 | 24 routes |
| Database | Firestore (Native, nam5) | 10 collections |
| Identity | Firebase Auth (email/password) | uid *is* the `User.id` |
| Object storage | Cloud Storage | `{project}-item-photos`, us-central1 |
| Email | Gmail SMTP + app password | no third-party mail service |
| Frontend | React 19, Vite 7, react-router-dom 7 | plain CSS custom properties, deliberately not Tailwind |

**Model tiering:** Flash by default everywhere. Pro is reserved for "complex
final reasoning" and is currently used nowhere — a live cost lever.

### 2.2 Size

| | Lines |
| --- | --- |
| Backend Python (incl. 11 test scripts) | ~7,400 |
| Frontend TS/TSX | ~3,800 |
| CSS | ~2,450 |

### 2.3 Backend module map

| Module | Lines | Responsibility |
| --- | --- | --- |
| `api.py` | 1401 | The whole HTTP surface. 24 routes. |
| `marketplace.py` | 301 | Tier 2 — platform, price, draft listing copy |
| `messages.py` | 285 | Unified feed + the two agent message behaviours |
| `items.py` | 260 | Item writes, photo URLs, soft delete, suggestion recompute |
| `models.py` | 250 | Pydantic entities; mirrors the data model doc |
| `dispositions.py` | 246 | Executor's final call, and advancing it to done |
| `mailer.py` | 242 | Invitation email over Gmail SMTP |
| `classify.py` | 239 | Photo → four `ai_*` fields, via Vertex |
| `overrides.py` | 227 | **The adaptive suggestion loop** |
| `membership.py` | 208 | Auth users, invites, accept, role lookup, member list |
| `claims.py` | 190 | Claim record/withdraw + status recomputation |
| `agent.py` | 185 | The ADK layer wrapping the two behaviours |
| `resolutions.py` | 140 | Executor settles a contested/claimed item |
| `photos.py` | 94 | Cloud Storage upload |
| `auth_deps.py` | 66 | ID token verification as a FastAPI dependency |
| `firebase_app.py` | 25 | One Firebase app per process |

---

## 3. Data model

Ten Firestore collections.

### 3.1 Entities

**`estates`** — `id`, `name`, `executor_user_id`, `status` (`active|closed`), `created_at`

**`users`** — `id` (= Firebase Auth uid), `email`, `display_name`, `role_type`
(`human|agent`), `created_at`
→ *The agent posts messages through this same table as a `role_type: agent` user
(`steward-agent`) with no Auth account. This is why the feed needs no separate
"system message" concept.*

**`estate_memberships`** — `id`, `estate_id`, `user_id`, `role`
(`executor|beneficiary`), `invited_at`, `accepted_at` *(null = pending)*
→ Deterministic id: `{estate_id}__{user_id}`

**`items`** — `id`, `estate_id`, `photo_urls[]`, `ai_category`,
`ai_condition_notes`, `ai_est_era_or_brand?`, `ai_classification_confidence`
(0–1), `suggested_disposition`, `status`, `created_at`

**`claims`** — `id`, `item_id`, `user_id`, `claimed_at`, `comment?`
→ **No uniqueness constraint, by design.** Repeat claims are recorded; distinct
claimant count drives status.

**`messages`** — `id`, `estate_id`, `item_id?` *(null = general)*, `user_id`,
`text`, `created_at`
→ **One unified feed, append-only.** The per-item thread is this data filtered.

**`resolutions`** — `id`, `item_id`, `resolved_by_user_id`, `resolution_type`,
`resolved_to_user_id?`, `notes`, `resolved_at` → `resolution__{item_id}`

**`dispositions`** — `id`, `item_id`, `channel`, `status`, `completed_at?`
→ `disposition__{item_id}`. **The extension seam** — Tier 2 and Tier 3 attach
here and never touch Item, Claim, or Resolution.

**`override_logs`** — `id`, `estate_id`, `item_id`, `item_category`
*(denormalised)*, `ai_suggested_disposition`, `executor_chosen_disposition`,
`created_at` → `override__{item_id}`. **Every** finalised decision is logged, not
only disagreements — the suggestion weights on total outcomes.

**`marketplace_listings`** *(Tier 2)* — `id`, `disposition_id`, `platform`,
`platform_recommendation_reason`, `suggested_price?`, `listing_draft_title?`,
`listing_draft_description?`, `listing_url?`, `listing_status`
→ `listing__{disposition_id}`

### 3.2 Deterministic IDs as an architectural choice

Every derived entity uses a computed document id rather than a query:
`resolution__{item}`, `disposition__{item}`, `override__{item}`,
`listing__{disposition}`, `{estate}__{user}`, `agent-mediate__{item}`.

1. **Idempotency is free** — re-running any write replaces rather than stacks.
2. **No composite indexes, no eventual-consistency window** on hot paths.
3. **Batched composition is cheap** — the review table pulls every item with its
   claims, resolutions, dispositions and listings in ~5 reads via `get_all`,
   not 114 round trips.

### 3.3 Enumerations

| Enum | Values |
| --- | --- |
| `ItemStatus` | `unclaimed`, `claimed`, `contested`, `resolved`, `routed`, `needs_clarification`, **`removed`** |
| `SuggestedDisposition` | `discard`, `donate`, `sell`, `uncertain` |
| `DispositionChannel` | `discard`, `donate`, `sell_marketplace`, `sell_auction_bulk` *(Tier 3, never written)* |
| `DispositionStatus` | `pending`, `in_progress`, `completed` — **all three now written** |
| `ResolutionType` | `assigned_to_claimant`, `rotation`, `outside_appraisal`, `executor_override` |
| `Platform` | `vinted`, `fb_marketplace`, `ebay`, `poshmark`, `other` |
| `ListingStatus` | `draft`, `posted`, `sold`, `removed` — **only `draft` is ever written** |
| `MembershipRole` | `executor`, `beneficiary` |

`removed` was added 2026-08-15 as a schema change and logged in the data model
doc. It needed no new checks anywhere: every status gate in the codebase is an
*allow-list* (`CLAIMABLE_STATUSES`, `RESOLVABLE_STATUSES`,
`SUGGESTION_ELIGIBLE_STATUSES`), so removed items fall out of claiming,
resolving and suggestion recompute by construction.

---

## 4. State machines

### 4.1 Item status

```
        photo upload (POST /estates/{id}/items)
             │
       ┌── classify ──┐
   conf ≥ 0.6     conf < 0.6
       │              │
       ▼              ▼
   unclaimed   needs_clarification ──► [agent asks a clarifying question]
       │
       │ ◄──────── DELETE /claim (withdraw)
       │  1 claimant
       ▼
    claimed ◄──────► contested ──► [agent posts mediation]
       │  2+ claimants  │
       └──────┬─────────┘
              │ POST /resolve
              ▼
          resolved
              │ POST /disposition          (writes Disposition: pending)
              │ POST /disposition/advance  → in_progress
              ▼
           routed        (…advance again → Disposition: completed)

  any status ──► removed   (POST /remove, executor only)
```

**Status is derived, never asserted.** `status_for_claimant_count()`: 0 →
`unclaimed`, 1 → `claimed`, 2+ → `contested`, counted on *distinct* `user_id`s.
`recompute_item_status` is the single implementation, used by both claim and
withdraw — the way down is the way up in reverse.

**Mediation posts only on the transition *into* contested**, so a withdrawal
that settles an item back down says nothing.

**Simultaneous claims are not a race to prevent.** Both get recorded; 2+ already
means contested.

### 4.2 Disposition status

`pending` → `in_progress` → `completed`. One step per call, each corresponding
to something that happened in the world. `in_progress` flips the item to
`routed`; `completed` stamps `completed_at`.

**Completion gets no new Item status, deliberately.** Disposition is given its
own `status` and `completed_at` precisely so the fulfilment lifecycle lives
there, and the data model doc's seam note says every tier's detail *"lives in
tables that reference Disposition, never in Item/Claim/Comment/Resolution
themselves."* An eighth Item status meaning "gone" would push disposition detail
back up into Item and create a second source of truth that could disagree with
`completed_at`. **Item.status answers "where did this land in the claim flow";
Disposition answers "and has it actually gone yet."**

---

## 5. AI functionality

Four Gemini touchpoints. All degrade to a visible, honest statement.

### 5.1 Photo classification (`classify.py`)

Input: image bytes. Output: exactly four schema-constrained fields.

- The prompt asks for a **calibrated** probability and says *"a family is going
  to act on this."*
- Below **0.6**, the item routes to `needs_clarification` instead of being
  guessed at.
- Blank/unreadable images are instructed to return `category: "unknown"` with
  confidence < 0.2 rather than inventing an object.
- **Failure path:** transport error, quota rejection, or unparseable reply all
  return confidence `0.0` with *"Couldn't classify this one — take a look?"*,
  routed through the *same* threshold. An upload never fails.

`classify_bytes(data, mime_type)` is the single implementation;
`classify_image(path)` reads a file and calls it. A photo arriving over HTTP
takes exactly the same path as one on disk — same prompt, schema, threshold and
failure handling, no temp file.

### 5.2 Agent behaviour A — clarifying question

**Trigger:** item enters `needs_clarification`. A state transition the backend
detects, *not* a model decision — dispatch is a dict lookup (`TOOL_FOR_STATUS`),
so the behaviour can't be missed at the mercy of a sampling temperature.

Posts to the family feed as the agent user, phrased as *"My best guess is
{category}."* Idempotent via deterministic message id.

### 5.3 Agent behaviour B — contested mediation

**Trigger:** item enters `contested` (2+ distinct claimants).

Names who asked, quotes what each said, and **proposes a resolution path in
prose** — not a bulleted menu. Never takes a side. Idempotent via
`agent-mediate__{item_id}`.

This is the emotional core and the hardest thing to copy well: the output is a
paragraph a family can read at a kitchen table, not a decision-support widget.

### 5.4 The adaptive suggestion loop (`overrides.py`) — track-critical

**The agent learns each estate's habits and says so out loud.**

```
suggest_disposition(estate_id, category, baseline, confidence, identified)
  ├─ not identified?  → "I couldn't identify this one well enough…"
  │                      (never applies a real pattern to a guess)
  ├─ history < 1?     → baseline + "There's no pattern yet for this estate…"
  ├─ dead heat?       → baseline + "This estate is evenly split on armchairs
  │                      (2 donated, 2 sold), so there's no pattern to lean on."
  └─ clear majority?  → that choice + "This estate has donated 4 of 5 armchairs
                         so far, so I'm leaning donate here too."
```

1. **Category counting, not vector retrieval.** An explicit non-goal — no
   embeddings, no similarity search. Cheap, fast, fully explainable.
2. **A tie is reported as a tie.** The system refuses to manufacture a pattern
   from a 2–2 split. The single most defensible detail in the whole design.
3. **The reason string is user-facing.** Every suggestion carries its own
   justification with real counts. No unexplained recommendation anywhere.

`recompute_suggestion(item_id)` lets an existing item catch up when the estate's
history changes underneath it, bounded to eligible statuses.

### 5.5 Marketplace listing draft (Tier 2, `marketplace.py`)

**One Gemini call produces all four fields** — they condition on each other.
Observed live: a brass lamp went to Facebook Marketplace *because* it was
"awkward and fragile to post with its shade", and that same fact set its price
and its wording.

- `platform` — schema-constrained to five values
- `platform_recommendation_reason` — one sentence, item-specific, family-facing
- `suggested_price` — a number, validated (rejects negatives, NaN, > $1M)
- `listing_draft_title` — short, no shouting
- `listing_draft_description` — 2–3 sentences that **must name the damage**

The prompt forbids inventing detail not in the condition notes, so thin notes
produce a short description rather than a padded one.

**Guard rails:** only a `sell_marketplace` disposition is eligible; donate,
discard and no-disposition all raise `MarketplaceError` (409). A partial reply
keeps what worked and nulls only the unusable field.

The test suite asserts against a reseller-hustle word list ("maximise", "act
fast", "rare find", "must see", "L@@K", "won't last") *and* checks for shouted
capitals — an automated brand-voice regression test.

---

## 6. API surface

24 routes. All authenticated except `/healthz`.

### 6.1 Reads

| Endpoint | Who | Notes |
| --- | --- | --- |
| `GET /healthz` | anyone | no token |
| `GET /estates/{id}/me` | any signed-in caller | role, `estate_name`, `invite_pending`. **Not a 403 for non-members** |
| `GET /estates/{id}/items` | accepted member | excludes removed; includes `decided_channel` |
| `GET /estates/{id}/members` | accepted member | accepted + pending, names resolved from `users` |
| `GET /estates/{id}/messages` | accepted member | the whole unified feed |
| `GET /estates/{id}/review` | accepted member | **composed**: items + claims + resolutions + dispositions + listings |
| `GET /items/{id}` | accepted member | readable even when removed |
| `GET /items/{id}/messages` | accepted member | per-item thread |
| `GET /items/{id}/claims` | accepted member | `count` (documents) and `claimant_count` (people) |
| `GET /items/{id}/resolution` | accepted member | **null, not 404** |
| `GET /items/{id}/disposition` | accepted member | **null, not 404**; nests the listing |

### 6.2 Writes

| Endpoint | Who | Notes |
| --- | --- | --- |
| `POST /estates/{id}/invite` | **executor** | creates the Auth account, emails a real sign-in link |
| `POST /estates/{id}/accept` | the invitee | returns `first_accept` |
| `POST /estates/{id}/items` | **executor** | **photo → classify → Item.** The entry point. |
| `POST /estates/{id}/messages` | accepted member | `item_id` nullable |
| `POST /items/{id}/claim` | accepted member | recomputes status; may fire mediation |
| `DELETE /items/{id}/claim` | **the claimant themselves** | withdraws own claim; recomputes status |
| `POST /items/{id}/photo` | **executor** | appends to an existing item |
| `POST /items/{id}/remove` | **executor** | soft delete |
| `POST /items/{id}/resolve` | **executor** | |
| `POST /items/{id}/disposition` | **executor** | writes Disposition **and** OverrideLog |
| `POST /items/{id}/disposition/advance` | **executor** | one step along the fulfilment track |
| `POST /items/{id}/marketplace-listing` | **executor** | Tier 2; real Gemini call |
| `POST /items/{id}/agent-message` | accepted member | runs the behaviour for the item's state through ADK |

### 6.3 Verb choices, stated

- **`POST /items/{id}/remove`, not DELETE** — DELETE promises the resource goes
  away and it does not. The document stays, its claims and messages stay
  attached, the URL keeps working.
- **`DELETE /items/{id}/claim`, and it means it** — the Claim documents
  genuinely go away. There is no withdrawn flag on Claim, and inventing one
  would be a schema change to record an absence the collection already expresses
  by not containing the row.
- **`/disposition/advance` nested** — what moves is the Disposition; the item's
  status change is a consequence.

### 6.4 Status-code contract

| Code | Meaning |
| --- | --- |
| 401 | no or invalid ID token |
| 403 | `MembershipError` — wrong role or not a member |
| 404 | no such item / no invite to accept / no claim of yours to withdraw |
| 409 | state conflict (`ClaimError`, `ResolutionError`, `DispositionError`, `MarketplaceError`) |
| 413 | photo over 12MB |
| 422 | unusable photo type |

### 6.5 Design principles visible in the API

- **Authorization lives only in `require_role`**, never duplicated in routes.
- **No user id in any request body.** The uid comes from the verified token, so
  a caller can only ever act as themselves — which is how "you can't withdraw
  someone else's claim" is guaranteed *structurally* rather than by a check.
- **Reads are permissive, writes are strict.** Any accepted member can read the
  claim list, the member list, and every decision. Inside a family, "who else
  wants this" is not privileged information.
- **Null, not 404,** for decisions that haven't been made — not having decided
  is the ordinary state, not a missing resource.
- **Composed endpoints over chatty ones.**

---

## 7. Frontend

Six routes, eight screens, nine components.

| Route | Screen | Function |
| --- | --- | --- |
| *(not addressable)* | **Sign in** | Email/password on a full-bleed gable photograph. Carries "Forgot your password?" as the invited person's way in. |
| *(gate)* | **Welcome** | 3 steps (4 for executors), shown once. Skippable. |
| `/` | **Dashboard** | Ledger blocks, six status filters, item grid, **"Add an item"** |
| `/items/:id` | **Item detail** | Placard, facts, claim/withdraw, who's asked, where it goes + fulfilment, thread, photo upload, remove |
| `/items/:id/resolve` | **Contested resolution** | Executor-only. Four resolution types, each explained. Claimant picker, never free text. |
| `/messages` | **Message Center** | Estate-wide unified feed + compose |
| `/review` | **Review table** | Executor-only. Grouped by what needs deciding. |
| `/family` | **Family** | Who's here, who's waiting, and the invite form |

### 7.1 Notable interaction decisions

**`<Arrival>` gate.** Fetches `/me` once; if an invite is pending it accepts it
automatically (they already followed the link — nothing to decide) and shows the
walkthrough only if that acceptance was the flip. **"Once" is derived from
server state, not a stored flag.**

**Adding an item names its wait in two parts** — *"Sending the photo…"* then
*"Steward is looking at it…"* once the Gemini call is where the time goes. It
lands on the new item's page, not back on a grid.

**Where the inline action stops.** A `claimed` item has one name on it, so the
review table settles it in one click. A `contested` item links out to the full
screen — settling that from a table would mean choosing between two people
without reading why either wants it. *Speed is deliberately not optimised at
that moment.*

**"Sell it" is one action, not two.** Choosing sell records the disposition
*and* requests the channel recommendation in the same click.

**Fulfilment in the words of the event.** *Mark it as dropped off* → *Mark it as
taken*; *Mark it as listed* → *Mark it as sold*. Never `in_progress` /
`completed`. The panel reads *Not dropped off yet* → *Dropped off* → *Given away
— August 16, 2026*, and the button disappears at the end.

**Withdrawal sits on your own row** in "Who's asked", not as an action on the
item — changing your mind, or standing aside so a sibling can have something, is
ordinary rather than a decision about the object.

**Removal sits last on the page**, quiet and underlined, sage rather than red.
Removing a duplicate photograph is housekeeping, not a danger.

**Completed states replace controls**, read back from storage so they survive a
reload.

**Sign-out clears the URL.** On a shared laptop the next person shouldn't land
where the last one was reading. A deep link followed *while signed out* still
lands where it pointed.

### 7.2 Design system — "Hearth & Archive"

Warm clay `#8e4831` primary, soft sage `#d7e8c8` secondary, warm cream surfaces,
**Ink `#211a14`** reserved for arrival moments only (sign-in, the estate hero,
the welcome). Not a dark mode; nothing toggles. Source Serif 4 + Work Sans.
Chips are **archival tags** at 3px radius, never pills; actions always pills.
**No shadows anywhere.**

### 7.3 Accessibility (WCAG 2.1 AA)

Audited 2026-08-15 with computed ratios. 32 pairings, 5 failed, all fixed.

- `outline` `#87736d` → **`#71615c`** (was 3.64–4.46:1 across six light
  surfaces; now 4.80–5.89:1)
- New `field-border` **`#988782`** for control edges (was 1.55:1 — 1.4.11 wants 3:1)
- **Colour is never the only signal:** each status chip carries a drawn mark —
  open ring, filled ring, two overlapping rings, tick, arrow, question mark,
  ringed strike-through — verified distinguishable under `grayscale(1)`
- Every screen has a `<main>` landmark; **zero unnamed interactive controls**
  across all six screens, confirmed against the live accessibility tree
- Item photos get generated alt text from the classifier's own output

---

## 8. Identity, roles, and permissions

The **Firebase Auth uid is the `User.id`**, so a verified token's uid goes
straight into a role check. `verify_id_token` runs with `clock_skew_seconds=30`.
Roles are **per estate**. A pending invite grants **no** role.

| Action | Beneficiary | Executor |
| --- | --- | --- |
| Read items, claims, messages, decisions, members | ✅ | ✅ |
| Claim an item | ✅ | ✅ |
| **Withdraw own claim** | ✅ | ✅ |
| Post to the feed | ✅ | ✅ |
| Trigger an agent behaviour | ✅ | ✅ |
| **Create an item from a photo** | ❌ | ✅ |
| Upload a photo to an existing item | ❌ | ✅ |
| Resolve a contested item | ❌ | ✅ |
| Record / advance a disposition | ❌ | ✅ |
| Request a marketplace listing | ❌ | ✅ |
| Remove an item | ❌ | ✅ |
| Invite someone | ❌ | ✅ |

Enforced server-side in `require_role` on every write. The frontend uses `/me`
only to decide what to *offer*.

**Firestore Security Rules** cover all 10 collections plus a default-deny
catch-all, tested with 48 emulator cases. `removed` is deliberately **not** in
the client-writable status list — that rule can only check membership, and
removal is executor-only, so it must go through the API.

---

## 9. The invitation flow

```
executor fills the Family form (email, name, role)
  → POST /invite  (create_account: true)
      ├─ auth.create_user(email)              → account with NO password provider
      ├─ invite_to_estate()                   → membership row, accepted_at = null
      ├─ auth.generate_password_reset_link()  → real Firebase action link
      └─ smtplib → Gmail SMTP                 → warm, plainspoken email
  → invitee follows the link, sets a password, signs in
  → <Arrival> accepts the pending invite
  → Welcome walkthrough runs once
```

**Verified end to end** against a real inbox using the exact link that was sent.

1. **The invite claims the address** — after an invite, that email returns
   `EMAIL_EXISTS` on self-registration, so the invitee cannot get in without the
   emailed link (or the sign-in screen's "Forgot your password?").
2. **The email is a courtesy, never a gate.** `send_invite_email` has no
   exception path. Missing credentials, a rejected login, or a dropped
   connection all return `invite_email_sent: false` with a plain note, and the
   invite still returns 200.
3. **Reserved domains are skipped before SMTP opens.** `example.com`, `.test`,
   `.invalid` and friends can never receive mail; attempting delivery only
   generated bounce notices in the sending account's inbox on every test run.

---

## 10. Failure handling — the governing principle

> Every failure mode degrades to a **visible, honest agent statement** — never a
> silent guess, never a blocked flow.

| Failure | Behaviour |
| --- | --- |
| Classification fails | Item → `needs_clarification`, "Couldn't classify this one — take a look?" Upload succeeds. |
| Simultaneous claims | Both recorded. 2+ = contested by design. |
| OverrideLog empty | "There's no pattern yet for this estate" |
| OverrideLog tied | "This estate is evenly split on armchairs (2 donated, 2 sold)" — refuses to invent a pattern |
| Marketplace call fails | `platform: other` + "Couldn't work out the best place for this one" |
| Marketplace partial reply | Keeps platform and reason, nulls only the unusable field |
| Price/copy unusable | "No price or wording came back for this one — worth writing it yourself" |
| Invite email fails | Invite succeeds; UI says the send failed and that the executor is the fallback |
| Link generation fails | Invite succeeds; UI says so |
| Item removed | Soft delete — document, claims and messages all stay; URL keeps working |
| Contested item settles back down | Mediation message stays as history but stops being promoted |
| Unrecognised item status from the API | Rendered as itself rather than swallowed |

---

## 11. Operations

### 11.1 Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `GOOGLE_CLOUD_PROJECT` | GCP project | `steward-hackathon-505217` |
| `VERTEX_LOCATION` | Vertex region | `global` |
| `GEMINI_MODEL` | model id | `gemini-3.5-flash` |
| `STEWARD_ALLOWED_ORIGINS` | CORS allow-list | localhost:5173/5174 |
| `STEWARD_APP_URL` | invite link `continueUrl` | unset |
| `STEWARD_WEB_API_KEY` | Identity Toolkit key (test tokens) | — |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` | SMTP | — (gitignored `backend/.env`) |
| `VITE_ESTATE_ID` | the estate the frontend addresses (build-time) | `seed-estate-001` |
| `VITE_API_BASE_URL` | backend origin | derived from hostname |

Credentials are ADC throughout — **no service-account key material anywhere.**

CORS `allow_methods` is an explicit `["GET", "POST", "DELETE"]`, not `"*"` —
nothing here should ever be reachable by PUT or PATCH.

### 11.2 Testing

Eleven standalone scripts (`test_*.py`) against **real Firestore and real
Gemini** — not pytest, not mocks. All passing. Plus 48 Security Rules emulator
cases and Playwright/Chromium driving the real app.

The suites assert on *quality*, not just shape: that a marketplace reason draws
≥2 distinctive words from the item's own record, that two items in different
categories get substantively different reasons, that listing copy contains no
reseller language and no shouted capitals.

**Caution for anyone running these:** they drive the real FastAPI app in-process
via `TestClient`, so they execute real side effects — Firestore, Cloud Storage,
Vertex, and Gmail.

### 11.3 Deployment status

**Nothing is deployed.** Cloud Run and `firebase deploy` are both still ahead.

- Item photos are in a **public-read bucket** with uuid4 paths — demo-only,
  because signed URLs need a service-account key and the project runs on user
  ADC. Two documented ways out.
- The real domain must be added to Firebase Auth's authorized domains and to
  `STEWARD_ALLOWED_ORIGINS`.
- Gmail SMTP will not scale past demo volume.

### 11.4 Bugs worth recording

All of these were invisible until something exercised them, and all are the kind
that survive a demo and fail in front of a user.

**The contested flow was unreachable from the UI.** The frontend's
`CLAIMABLE_STATUSES` was `['unclaimed', 'contested']` — `claimed` was missing,
so once one person had asked for something, *nobody else could ask*. Every
contested item in the demo got there by script. This is the centre of the whole
product, and two people using the app could not produce it. Fixed to mirror the
backend's set.

**The claim form never changed state once you had claimed.** It stayed fully
live, so a second click filed a real duplicate Claim for the same person — found
in manual UAT, with a genuine duplicate sitting in the demo data. The backend
behaviour was correct (repeat claims are deliberate, and status counts distinct
claimants); the UI simply never said "you've already asked".

**"Settled" meant two things on one screen.** The dashboard's summary card
counted `resolved + routed` while the filter tab beneath it counted `resolved`,
so the same word showed 14 and 13 side by side. `Settled` and `On its way` are
distinct words this app teaches people; the card was the one inventing a second
meaning.

**`clear_decision` left an incoherent state.** It dropped the Disposition
without undoing its effect on the item, leaving a `routed` item with nothing
routing it — and the next decision was then refused, because only a resolved
item is eligible. Surfaced by `test_marketplace` immediately after fulfilment
landed.

---

## 12. What is *not* built — the enhancement surface

### 12.1 Deliberately out of scope (Tier 3)

| Not built | Why |
| --- | --- |
| Bulk auction / estate-sale batch pricing | Schema scaffolded (`sell_auction_bulk`, never written), cut first under time pressure |
| **Actual API posting to marketplaces** | Draft only. Cost control + demo scope. `listing_url` and `listing_status` beyond `draft` are never written. |
| Donation receipt / tax-value documentation | Out |
| Payment or commission handling | Out |
| Vector / semantic retrieval for OverrideLog | **Explicit non-goal** — category counting is the design |

### 12.2 Gaps in what *is* built

Ranked roughly by how much they'd hurt a real user.

| Gap | Notes |
| --- | --- |
| **No direct edit of AI fields** | `POST /items/{id}/clarify` now lets any member answer the agent's question and have it re-read the item — so the loop is closed for `needs_clarification`. What is still missing is editing an item the agent was *confident* about and got wrong: there is no path to correct a high-confidence misread. |
| **Shared-memories agent behaviour** | A third behaviour prompting family to share stories about an item when someone comments. On-brand, unbuilt, and the highest-value *addition* rather than fix. |
| **Notifications cover two moments, not all of them** | An item becoming contested and a resolution being recorded both email every claimant. Nothing else does — a new claim, an agent's clarifying question, or a disposition advancing are all still silent. And there are **no preferences and no unsubscribe**, which has to land before anything chattier is added. |
| **No mobile capture flow** | "Add an item" is a file picker. On a phone it will offer the camera, but there is no walk-the-house capture loop, no `capture` hint, no queue. The obvious real-world entry point is one step short. |
| **No bulk upload** | One photo, one item, one request, one Gemini call. Six things means six waits. |
| **No search or sort** | Six status filters only. No text search across 40+ items, no sort by anything. |
| **Nothing is reversible** | Removal, disposition advancement, and resolution all move one way. A mis-click needs Firestore. |
| **No audit trail UI** | OverrideLog is written and read by the agent but never shown to a human. The executor cannot see their own decision history — the very thing the agent cites back at them. |
| **Single estate per deployment** | `VITE_ESTATE_ID` is build-time. Roles are modelled per estate correctly on the backend, but the client addresses one. No estate switcher, no estate creation UI. |
| **Membership is append-only** | A role can't be changed and nobody can be removed from an estate. |
| **`ListingStatus` never moves** | `posted`, `sold`, `removed` are defined and unused — the same gap `DispositionStatus` had until this week. |
| **Pro model unused** | Reserved for "complex final reasoning", used nowhere. |

### 12.3 Competitive read

**Defensible today:**
- The adaptive loop that explains itself with real counts and **refuses to
  invent a pattern from a tie**. Most competitors either don't adapt or adapt
  opaquely.
- Mediation output that reads as prose a family can act on, with a proposed path
  and no side taken.
- The failure-handling discipline — every degraded path produces a sentence a
  non-technical person can act on. This is the difference between a product and
  a Gemini wrapper.
- The plain-language vocabulary and anti-urgency constraint set. A genuine wedge
  against reseller-flavoured competitors.
- One Gemini call producing platform + price + copy that mutually agree.
- The full arc now runs end to end: **photograph → classify → claim → contest →
  mediate → resolve → route → gone.**

**Thin today:**
- **The conversation is one-way.** The agent asks clarifying questions and
  nobody can answer them in a way the system understands. Closing that loop —
  letting a reply correct the classification — would make the "collaborative
  partner" claim true in both directions rather than one.
- **Nothing reaches out.** Without notifications, a multi-user product depends
  on everyone independently remembering to visit.
- **Ingestion is one photo at a time.** Fine for a demo, painful for a house.
- **The beneficiary's experience is thin.** They can browse, claim, withdraw and
  talk — but every affordance that creates momentum is unbuilt. The product is
  still executor-shaped.

---

## 13. Reference

| Document | Contents |
| --- | --- |
| `docs/estate-agent-RDD.md` | Original scope, demo arc, tier boundaries, prize tracks |
| `docs/estate-agent-data-model.md` | Canonical schema — **source of truth for entities** |
| `docs/estate-agent-branding.md` | Voice, visual persona, what the brand rules out |
| `docs/design/steward/DESIGN.md` | The design system — **source of truth for visual style** |
| `backend/README.md` | Endpoint detail, agent behaviours, auth-path probes |
| `frontend/README.md` | Screen-by-screen rationale, accessibility audit table |
| `CLAUDE.md` | Working constraints and tripwires |

### Commands

```bash
cd backend  && .venv/bin/uvicorn api:app --reload --port 8000   # API
cd frontend && npm run dev                                      # :5173
cd backend  && .venv/bin/python test_<name>.py                  # one suite, real Firestore
cd backend  && .venv/bin/python seed_demo_items.py              # 14 demo items
cd frontend && node verify.mjs                                  # drive the real app in Chromium
cd rules-tests && npm test                                      # Security Rules (needs Java 21)
```
