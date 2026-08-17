"""A rough sense of what a belonging is worth, for items nobody is selling.

**Why this exists as a separate, smaller call.** `marketplace.py` already
produces a `suggested_price`, but only for items routed to `sell_marketplace` —
and those go to a buyer, not to a family member. Measured on the seeded estate:
four items carry a real price, eleven went to a named person, and the overlap
between those two sets is **zero**. So a "how has it landed" view built only on
existing pricing data would have nothing at all to show. The estimate has to be
generated for the items people actually kept.

It is deliberately much smaller than the marketplace pipeline: one number and
one short reason, no platform, no listing copy. A rough order of magnitude is
all the question needs, and asking for more would cost more and imply a
precision nobody has.

**Framed the same honest way `suggested_price` is**, and for the same reason: a
model looking at a category and a condition note is guessing, and a family
making decisions deserves to know that. Nothing here is an appraisal.

Cached under a deterministic id so a page view costs nothing after the first —
`valuations` is a post-RDD addition, noted in the data model doc.
"""

import json
import logging
from typing import Optional

from google.genai import types
from pydantic import BaseModel

from classify import model_name, vertex_client
from firebase_app import get_db
from models import Item

logger = logging.getLogger(__name__)

COLLECTION = "valuations"

# Above this, a single object would dominate any tally and is almost certainly
# a model error rather than a Ming vase in a suburban hallway.
MAX_SENSIBLE = 100_000.0


class Valuation(BaseModel):
    """A rough second-hand value for one item. Not an appraisal."""

    id: str
    item_id: str
    estate_id: str
    # Null when the model could not give a usable number. The view must show
    # that as "no estimate yet", never as zero — an unvalued chair is not a
    # worthless chair.
    rough_value: Optional[float] = None
    reason: str = ""


PROMPT = """A family is sorting out a house after a death. Estimate roughly what this
household item would fetch second-hand, in US dollars.

  category  : {category}
  condition : {condition}
  era/brand : {era}

Most household belongings are worth very little — ordinary crockery, worn
linens and mass-produced furniture are usually under fifty dollars, often under
ten. Say so plainly rather than inflating. Only go high when the era or brand
genuinely warrants it.

Give a single number a person would recognise as a ballpark: 5, 20, 40, 150.
Then one short clause saying what it rests on.

Reply with JSON only:
{{"rough_value": 0, "reason": "a few words"}}"""


def valuation_id(item_id: str) -> str:
    return f"valuation__{item_id}"


def get_valuation(item_id: str) -> Optional[Valuation]:
    snapshot = get_db().collection(COLLECTION).document(valuation_id(item_id)).get()
    return Valuation.model_validate(snapshot.to_dict()) if snapshot.exists else None


def _ask(item: Item) -> tuple[Optional[float], str]:
    """One small call. Any failure comes back as "no estimate", never as zero."""
    try:
        response = vertex_client().models.generate_content(
            model=model_name(),
            contents=PROMPT.format(
                category=item.ai_category,
                condition=item.ai_condition_notes,
                era=item.ai_est_era_or_brand or "not established",
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "rough_value": types.Schema(type=types.Type.NUMBER),
                        "reason": types.Schema(type=types.Type.STRING),
                    },
                    required=["rough_value"],
                ),
            ),
        )
        payload, _ = json.JSONDecoder().raw_decode((response.text or "").strip())
        value = float(payload["rough_value"])
    except Exception:  # noqa: BLE001 — a failed estimate is an absent one
        logger.warning("could not estimate a value for %s", item.id, exc_info=True)
        return None, ""

    if value != value or value < 0 or value > MAX_SENSIBLE:
        return None, ""
    return round(value, 2), str(payload.get("reason") or "").strip()


def ensure_valuation(item: Item) -> Valuation:
    """The stored estimate for an item, generating it once if there isn't one.

    Idempotent by deterministic id: the first view of a settled estate pays for
    the estimates, every later one is a read.
    """
    existing = get_valuation(item.id)
    if existing is not None:
        return existing

    value, reason = _ask(item)
    valuation = Valuation(
        id=valuation_id(item.id),
        item_id=item.id,
        estate_id=item.estate_id,
        rough_value=value,
        reason=reason,
    )
    get_db().collection(COLLECTION).document(valuation.id).set(valuation.model_dump())
    return valuation
