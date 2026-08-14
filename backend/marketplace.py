"""Tier 2: which marketplace to sell a belonging on, and why.

**Channel recommendation only.** Pricing and draft listing text are separate,
later work — `suggested_price`, `listing_draft_title` and
`listing_draft_description` are written null, meaning "not done yet" rather than
"none needed".

Attaches at the Disposition seam, exactly as the data model doc describes: this
module reads a Disposition and writes a MarketplaceListing. Nothing in Tier 1
changes to accommodate it.

The Vertex client is the one classify.py already builds — one per process, not
one per module.
"""

import json
from typing import Optional

from google.genai import types

from classify import model_name, vertex_client
from dispositions import get_disposition
from firebase_app import get_db
from items import get_item
from models import (
    Disposition,
    DispositionChannel,
    ListingStatus,
    MarketplaceListing,
    Platform,
)

# What the executor sees when the model could not be reached or understood. Same
# principle as CLASSIFICATION_FAILED_NOTE: an honest "I don't know", never a
# guess dressed up as a recommendation.
RECOMMENDATION_FAILED_REASON = (
    "Couldn't work out the best place for this one — worth having a look "
    "yourself before it goes anywhere."
)


class MarketplaceError(Exception):
    """This disposition can't have a listing, and why.

    Raised rather than skipped: asking for a marketplace recommendation on a
    donate or discard decision is a mistake in the caller, and quietly returning
    nothing would hide it.
    """


PROMPT = """A family is settling an estate and has decided to sell one of the belongings.
Recommend where to list it.

The item:
  category: {category}
  condition: {condition}
  era or brand: {era}

Choose exactly one platform:
  vinted          — clothing, fabric, accessories; casual, low-value, easy postage
  fb_marketplace  — furniture and anything bulky or local-collection-only
  ebay            — collectables, tools, china, anything with a specialist buyer
  poshmark        — branded fashion and accessories, US-centric
  other           — none of the above genuinely fits

Then give one short sentence saying why, written for the family — not for a
reseller. Be specific to *this* item: name the thing, and the actual reason
(weight, buyer, condition, who looks there). Warm and plainspoken. No urgency,
no sales language, no talk of maximising returns or moving fast.

Good: "A bookcase this heavy is really a local-collection sale, and Facebook is
where people near you look."
Bad: "Maximise your resale value by listing on our recommended platform!"

Reply with JSON only:
{{"platform": "one of the five above", "reason": "one sentence"}}"""


def _response_schema() -> types.Schema:
    """Constrain generation so the platform can only be one of the five."""
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "platform": types.Schema(
                type=types.Type.STRING,
                enum=[platform.value for platform in Platform],
            ),
            "reason": types.Schema(type=types.Type.STRING),
        },
        required=["platform", "reason"],
    )


def listing_id(disposition_id: str) -> str:
    """Deterministic document id: one listing per disposition.

    A disposition is one decision about one item, so re-running a recommendation
    replaces the previous one rather than stacking drafts.
    """
    return f"listing__{disposition_id}"


def get_listing(disposition_id: str) -> Optional[MarketplaceListing]:
    """The listing for a disposition, or None if none has been drafted."""
    snapshot = (
        get_db()
        .collection(MarketplaceListing.COLLECTION)
        .document(listing_id(disposition_id))
        .get()
    )
    if not snapshot.exists:
        return None
    return MarketplaceListing.model_validate(snapshot.to_dict())


def _ask_gemini(category: str, condition: str, era: Optional[str]) -> tuple[Platform, str]:
    """Ask for a platform and a reason. Falls back honestly, never guesses.

    A transport failure, a quota rejection or an unparseable reply all come back
    as `other` with a plain note — the same shape classify.py uses, so a failure
    is visible in the data rather than hidden behind a plausible-looking choice.
    """
    try:
        response = vertex_client().models.generate_content(
            model=model_name(),
            contents=PROMPT.format(
                category=category, condition=condition, era=era or "not established"
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_response_schema(),
            ),
        )
        raw = (response.text or "").strip()
    except Exception:  # noqa: BLE001 — every failure degrades the same way
        return Platform.OTHER, RECOMMENDATION_FAILED_REASON

    try:
        payload, _ = json.JSONDecoder().raw_decode(raw)
        platform = Platform(payload["platform"])
        reason = str(payload["reason"]).strip()
    except Exception:  # noqa: BLE001 — a malformed reply is a failed reply
        return Platform.OTHER, RECOMMENDATION_FAILED_REASON

    if not reason:
        return platform, RECOMMENDATION_FAILED_REASON
    return platform, reason


def recommend_channel(item_id: str) -> MarketplaceListing:
    """Recommend where to sell a resolved item, and record it as a draft listing.

    Raises MarketplaceError if the item has no disposition yet, or if the
    disposition routes somewhere other than a marketplace. Both are caller
    mistakes worth surfacing — a donate decision does not silently acquire a
    marketplace listing.
    """
    disposition = get_disposition(item_id)
    if disposition is None:
        raise MarketplaceError(
            f"Item {item_id} has no disposition decision yet — the executor "
            "records one before there is anything to list."
        )

    if disposition.channel is not DispositionChannel.SELL_MARKETPLACE:
        raise MarketplaceError(
            f"Item {item_id} is going to {disposition.channel.value}, not a "
            "marketplace. Only a sell_marketplace disposition gets a listing."
        )

    item = get_item(item_id)
    if item is None:
        raise MarketplaceError(f"No item {item_id} to recommend a channel for.")

    platform, reason = _ask_gemini(
        item.ai_category, item.ai_condition_notes, item.ai_est_era_or_brand
    )

    listing = MarketplaceListing(
        id=listing_id(disposition.id),
        disposition_id=disposition.id,
        platform=platform,
        platform_recommendation_reason=reason,
        # Explicitly null: this loop is channel choice only.
        suggested_price=None,
        listing_draft_title=None,
        listing_draft_description=None,
        listing_url=None,
        listing_status=ListingStatus.DRAFT,
    )

    get_db().collection(MarketplaceListing.COLLECTION).document(listing.id).set(
        {
            "id": listing.id,
            "disposition_id": listing.disposition_id,
            "platform": listing.platform.value,
            "platform_recommendation_reason": listing.platform_recommendation_reason,
            "suggested_price": listing.suggested_price,
            "listing_draft_title": listing.listing_draft_title,
            "listing_draft_description": listing.listing_draft_description,
            "listing_url": listing.listing_url,
            "listing_status": listing.listing_status.value,
        }
    )
    return listing
