# Data Model — Estate Belongings Disposition Agent

Last updated: 2026-08-10
Design principle: Tier 1 (core) entities never change shape when Tier 2/3 are added. Later tiers attach via foreign keys to core tables — they extend, they don't modify. This means Tier 3 can be designed now and safely deferred without an architecture rewrite later.

---

## Tier 1 — Core (must work end-to-end for demo)

**Estate**
- id (PK)
- name
- executor_user_id (FK → User)
- status: active | closed
- created_at

**User**
- id (PK)
- email
- display_name
- role_type: human | agent — *"agent" lets Steward's own agent author Messages (clarifying questions, contested-item mediation) through the same table humans use, instead of a separate notification system*
- created_at

**EstateMembership** (join table — a user's role within a specific estate)
- id (PK)
- estate_id (FK → Estate)
- user_id (FK → User)
- role: executor | beneficiary
- invited_at
- accepted_at (nullable — pending invite if null)

**Item**
- id (PK)
- estate_id (FK → Estate)
- photo_url(s)
- ai_category (from Vision/ML Kit classification)
- ai_condition_notes
- ai_est_era_or_brand (nullable)
- ai_classification_confidence (0-1 — drives the clarifying-question trigger below)
- suggested_disposition: discard | donate | sell | uncertain — *informed by OverrideLog history for the estate, not a one-shot guess — see below*
- status: unclaimed | claimed | contested | resolved | routed | needs_clarification
- created_at

**OverrideLog** (the persistent-memory / adaptation mechanic — required for Collaborative Partner track eligibility)
- id (PK)
- estate_id (FK → Estate)
- item_id (FK → Item)
- item_category (denormalized copy of ai_category — avoids a join when weighting future suggestions)
- ai_suggested_disposition
- executor_chosen_disposition
- created_at

*Before suggesting a disposition on a new item, the agent retrieves this estate's override history (optionally filtered by category) and weights its suggestion accordingly — e.g., "this estate has donated 4 of 5 sentimental items so far, leaning donate here too." This is the retrieval-and-adapt loop the track brief explicitly requires ("learns your brand preferences from your corrections"). Without this table, Steward doesn't clear the track's stated technical bar.*

**Claim**
- id (PK)
- item_id (FK → Item)
- user_id (FK → User)
- claimed_at
- comment (nullable)

*An item with 1 claim → status becomes `claimed`. 2+ claims → status becomes `contested`.*

**Message** (the central messaging hub — single unified feed, not split by scope)
- id (PK)
- estate_id (FK → Estate)
- item_id (FK → Item, **nullable** — set when a message is about a specific item, null for general estate discussion)
- user_id (FK → User — may be a human or the `agent` role_type user)
- text
- created_at

*One feed serves human conversation ("planning the weekend visit") and agent-authored guidance alike. Two agent behaviors post here, both required by the Collaborative Partner brief:*
- *Clarifying questions: when `Item.ai_classification_confidence` is low, agent posts a question and flips item status to `needs_clarification`*
- *Contested-item mediation: the moment an item flips to `contested`, agent posts a mediating suggestion (assign/rotate/appraise) rather than leaving raw conflict data for the executor to interpret unaided*

*Promoted to Tier 1 — it's core to the experience (a primary nav tab alongside Inventory and History), not a stretch feature.*

**Resolution**
- id (PK)
- item_id (FK → Item)
- resolved_by_user_id (FK → User — must be executor role)
- resolution_type: assigned_to_claimant | rotation | outside_appraisal | executor_override
- resolved_to_user_id (nullable — set if assigned/rotation)
- notes
- resolved_at

*Resolution flips item status from `contested`/`claimed` → `resolved`. `resolved` items then become eligible for Disposition (below).*

**Disposition**
- id (PK)
- item_id (FK → Item)
- channel: discard | donate | sell_marketplace | sell_auction_bulk
- status: pending | in_progress | completed
- completed_at (nullable)

*This is the seam. Every item, regardless of tier, ends up here once resolved. Tier 2 and Tier 3 both attach additional detail to a Disposition row — they never need to touch Item, Claim, Comment, or Resolution.*

---

## Tier 2 — Stretch (marketplace channel research + pricing + listing)

**MarketplaceListing**
- id (PK)
- disposition_id (FK → Disposition, where channel = sell_marketplace)
- platform: vinted | fb_marketplace | ebay | poshmark | other
- platform_recommendation_reason (short text — why this platform was chosen for this item category)
- suggested_price
- listing_draft_title
- listing_draft_description
- listing_url (nullable until actually posted)
- listing_status: draft | posted | sold | removed

*Attaches cleanly to any Disposition row with channel = sell_marketplace. Nothing upstream changes.*

---

## Tier 3 — Defer-first (bulk auction/estate-sale pricing)

**AuctionBatch**
- id (PK)
- estate_id (FK → Estate)
- batch_pricing_method: bulk_ai_estimate | comparable_lot_pricing
- auction_house_id (nullable — if partnered/routed externally)
- submitted_at
- status: pending | submitted | completed

**AuctionBatchItem** (join table)
- id (PK)
- auction_batch_id (FK → AuctionBatch)
- disposition_id (FK → Disposition, where channel = sell_auction_bulk)
- batch_est_price

*Also attaches at the Disposition seam. If Tier 3 gets cut under time pressure, nothing in Tier 1 or Tier 2 needs to change — these two tables simply don't get built, and any `sell_auction_bulk` dispositions stay in `pending` status with no downstream table populated. Demo can describe this as "next system extension" on the roadmap slide without it looking bolted-on.*

---

## Why this holds up under the cut rule

The Disposition table is the deliberate seam point. Every tier-specific complexity (which marketplace, what price, which auction house) lives in tables that reference Disposition, never in Item/Claim/Comment/Resolution themselves. That means:

- Tier 1 alone is a complete, demoable system (classify → claim → contest → resolve → mark disposition intent) even with zero Tier 2/3 tables built.
- Tier 2 is additive — build it once Tier 1 is solid, no rework required.
- Tier 3 can be scaffolded (empty tables, migration written) without being populated by working logic — "designed for, not yet built" is a real, honest state, not a lie.
