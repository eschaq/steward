"""Tier 2: which marketplace to sell a belonging on, what to ask for it, and
how to describe it.

**One Gemini call for all four**, not a channel call followed by a pricing call.
They condition on each other: the same sideboard is worded and priced one way as
a local Facebook collection and another way as an eBay listing to a collector,
and a second call would be free to disagree with the first. Asking once also
halves the latency the executor waits through, and there is no case where a
caller wants the platform without the rest.

`listing_url` stays null — that is set when someone actually posts it somewhere,
which is a human act, not a generated one.

Attaches at the Disposition seam, exactly as the data model doc describes: this
module reads a Disposition and writes a MarketplaceListing. Nothing in Tier 1
changes to accommodate it.

The Vertex client is the one classify.py already builds — one per process, not
one per module.
"""

import json
from typing import NamedTuple, Optional

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
Work out where to list it, what to ask for it, and how to describe it.

The item:
  category: {category}
  condition: {condition}
  era or brand: {era}

**platform** — choose exactly one:
  vinted          — clothing, fabric, accessories; casual, low-value, easy postage
  fb_marketplace  — furniture and anything bulky or local-collection-only
  ebay            — collectables, tools, china, anything with a specialist buyer
  poshmark        — branded fashion and accessories, US-centric
  other           — none of the above genuinely fits

**reason** — one short sentence on why that platform, written for the family,
not for a reseller. Be specific to *this* item: name the thing, and the actual
reason (weight, buyer, condition, who looks there).

Good: "A bookcase this heavy is really a local-collection sale, and Facebook is
where people near you look."
Bad: "Maximise your resale value by listing on our recommended platform!"

**suggested_price** — a plain number in US dollars, no currency symbol, no
range. A sensible asking price on that platform for something in this condition.
Nobody expects an appraisal — this is a starting point the executor will adjust,
so a defensible ballpark beats a confident-sounding guess. Round to something a
person would actually type: 15, 40, 250. If the item is genuinely worth almost
nothing, say so with a low number rather than inflating it.

**listing_draft_title** — what goes in the listing's title field, under about 70
characters. Name the thing plainly, with the era or brand if it is real. No
capitals for emphasis, no exclamation marks, no "RARE", no "L@@K".

**listing_draft_description** — two or three short sentences the family could
post as written. Say what it is, then say what is wrong with it. Wear, damage
and missing pieces go in the description, not left for the buyer to find — a
family selling their parents' things is not trying to put one over on anyone.
Plain and unhurried. Never invent a detail that is not in the condition notes
above; if the notes are thin, the description is short.

Good: "A brass table lamp from the 1970s, rewired at some point and working. The
shade is original and has a small tear near the seam. Collection from the house,
or I can post it if you cover the cost."
Bad: "STUNNING vintage brass lamp!! A RARE FIND for the discerning collector —
won't last long at this price!"

Reply with JSON only:
{{"platform": "one of the five above",
  "reason": "one sentence",
  "suggested_price": 0,
  "listing_draft_title": "short title",
  "listing_draft_description": "two or three sentences"}}"""


def _response_schema() -> types.Schema:
    """Constrain generation so the platform can only be one of the five, and the
    price comes back as a number rather than "about $40"."""
    string = types.Schema(type=types.Type.STRING)
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "platform": types.Schema(
                type=types.Type.STRING,
                enum=[platform.value for platform in Platform],
            ),
            "reason": string,
            "suggested_price": types.Schema(type=types.Type.NUMBER),
            "listing_draft_title": string,
            "listing_draft_description": string,
        },
        required=[
            "platform",
            "reason",
            "suggested_price",
            "listing_draft_title",
            "listing_draft_description",
        ],
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


class Draft(NamedTuple):
    """Everything the one Gemini call comes back with.

    Price and the two draft-text fields stay Optional: a reply good enough to
    name a platform but not to price the thing is worth keeping for the part it
    got right, rather than being thrown away whole.
    """

    platform: Platform
    reason: str
    suggested_price: Optional[float] = None
    listing_draft_title: Optional[str] = None
    listing_draft_description: Optional[str] = None


# A price the model clearly didn't mean. Not a valuation judgement — just the
# range outside which a household belonging's asking price is a parse artefact.
MAX_SENSIBLE_PRICE = 1_000_000.0


def _price(value: object) -> Optional[float]:
    """A usable asking price, or None. Never a negative or a NaN."""
    try:
        price = round(float(value), 2)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if price != price or price < 0 or price > MAX_SENSIBLE_PRICE:
        return None
    return price


def _text(value: object) -> Optional[str]:
    """A non-empty string, or None — an empty draft is not a draft."""
    text = str(value).strip() if value is not None else ""
    return text or None


def _failed() -> Draft:
    """What comes back when the model could not be reached or understood.

    `other` with a plain note and nothing else filled in, the same shape
    classify.py uses: the failure is visible in the data rather than hidden
    behind a plausible-looking recommendation.
    """
    return Draft(platform=Platform.OTHER, reason=RECOMMENDATION_FAILED_REASON)


def _ask_gemini(category: str, condition: str, era: Optional[str]) -> Draft:
    """Ask for the platform, the reason, a price and the draft text — once.

    A transport failure, a quota rejection or an unparseable reply all degrade
    the same way. A reply that parses but leaves a field unusable keeps
    everything else and nulls only that field.
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
        return _failed()

    try:
        payload, _ = json.JSONDecoder().raw_decode(raw)
        platform = Platform(payload["platform"])
        reason = _text(payload.get("reason"))
    except Exception:  # noqa: BLE001 — a malformed reply is a failed reply
        return _failed()

    return Draft(
        platform=platform,
        reason=reason or RECOMMENDATION_FAILED_REASON,
        suggested_price=_price(payload.get("suggested_price")),
        listing_draft_title=_text(payload.get("listing_draft_title")),
        listing_draft_description=_text(payload.get("listing_draft_description")),
    )


def recommend_channel(item_id: str) -> MarketplaceListing:
    """Draft a listing for a resolved item: where, how much, and what to say.

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

    draft = _ask_gemini(
        item.ai_category, item.ai_condition_notes, item.ai_est_era_or_brand
    )

    listing = MarketplaceListing(
        id=listing_id(disposition.id),
        disposition_id=disposition.id,
        platform=draft.platform,
        platform_recommendation_reason=draft.reason,
        suggested_price=draft.suggested_price,
        listing_draft_title=draft.listing_draft_title,
        listing_draft_description=draft.listing_draft_description,
        # Set when someone actually posts it somewhere — a human act, not a
        # generated one.
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
