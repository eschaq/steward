"""Answering the agent's question, and doing something with the answer.

The agent posts a clarifying question when an item lands in
`needs_clarification`. Until now nothing could be done with a reply: the
question was real and the conversation was one-way. This closes it.

Not one of the two ADK behaviours in `agent.py`, deliberately. Those fire on a
*state transition* the backend detects — that is what keeps them from being
missed at the mercy of a sampling temperature. This one is triggered by a person
choosing to answer, which is a different kind of event and does not belong in
that dispatch table.

The shape of the exchange is three ordinary Messages in one thread — the agent's
question, the person's answer, the agent's reply — because a conversation that
reads as a conversation is the whole point. Nothing here is a hidden mechanism.
"""

from typing import NamedTuple, Optional

from classify import CONFIDENCE_THRESHOLD, classify_with_context, status_for_confidence
from firebase_app import get_db
from items import ItemError, get_item, suggestion_for
from membership import require_role
from messages import (
    clarification_followup_text,
    display_names_for,
    post_clarification_followup,
    post_message,
)
from models import Item, ItemStatus, Message
from photos import fetch_item_photo


class ClarificationError(Exception):
    """The clarification could not be applied, and why.

    Raised rather than swallowed — someone taking the trouble to answer deserves
    to be told if it went nowhere.
    """


class Clarification(NamedTuple):
    """What happened, in the terms the caller needs to report."""

    item: Item
    answer: Message
    reply: Optional[Message]
    cleared: bool
    confidence: float
    previous_category: str
    failed: bool


def _photo_for(item: Item) -> Optional[tuple[bytes, str]]:
    """The first stored photograph, if this item has one we can read back.

    `photo_urls` can also hold the local `file://` path the seed and test scripts
    record, which is not something this process can fetch — those come back None
    and the re-reading proceeds on the family's words alone.
    """
    for url in item.photo_urls:
        image = fetch_item_photo(url)
        if image is not None:
            return image
    return None


def respond_to_clarification(item_id: str, uid: str, text: str) -> Clarification:
    """Answer the agent's question about an item, and re-read the item with it.

    Any accepted member of the estate may answer — identifying a belonging is
    exactly the thing a family knows and the executor may not. Authorization is
    membership, not role.

    The answer is posted as an ordinary Message first, before anything else
    happens. If the re-reading then fails, what the person said is still in the
    thread where the family can see it; losing someone's words because a model
    call timed out would be the worst outcome here.

    Raises ClarificationError if the item does not exist, is not in
    `needs_clarification`, or the answer is empty.
    """
    answer = (text or "").strip()
    if not answer:
        raise ClarificationError("There's nothing in that reply to go on.")

    item = get_item(item_id)
    if item is None:
        raise ClarificationError(f"No item {item_id} to answer about.")

    # Authorization before anything is written, and before the item's state is
    # described back to a non-member.
    require_role(uid, item.estate_id)

    if item.status is not ItemStatus.NEEDS_CLARIFICATION:
        raise ClarificationError(
            f"Item {item_id} is {item.status.value} — the agent isn't waiting on "
            "anything for this one. Anything else you want to say about it can go "
            "in the thread."
        )

    # The person's words land in the feed first, and stay there whatever happens
    # next.
    posted = post_message(
        estate_id=item.estate_id, user_id=uid, text=answer, item_id=item_id
    )

    reading = classify_with_context(
        context=answer,
        previous_category=item.ai_category,
        previous_notes=item.ai_condition_notes,
        image=_photo_for(item),
    )
    failed = reading.error is not None
    cleared = (
        not failed and reading.ai_classification_confidence >= CONFIDENCE_THRESHOLD
    )

    updated = item
    if not failed:
        # The four ai_* fields are rewritten either way — even a re-reading that
        # stays under the threshold usually knows more than it did, and throwing
        # that away would make answering twice pointless. Status only moves when
        # the threshold is actually cleared.
        status = (
            status_for_confidence(reading.ai_classification_confidence)
            if cleared
            else ItemStatus.NEEDS_CLARIFICATION
        )
        suggestion = suggestion_for(item.estate_id, reading)
        fields = {
            "ai_category": reading.ai_category,
            "ai_condition_notes": reading.ai_condition_notes,
            "ai_est_era_or_brand": reading.ai_est_era_or_brand,
            "ai_classification_confidence": reading.ai_classification_confidence,
            "suggested_disposition": suggestion.suggested_disposition.value,
            "status": status.value,
        }
        get_db().collection(Item.COLLECTION).document(item_id).update(fields)
        updated = item.model_copy(
            update={**fields, "status": status,
                    "suggested_disposition": suggestion.suggested_disposition}
        )

    who = display_names_for([uid]).get(uid, "there").split(" ")[0]
    reply = post_clarification_followup(
        item.estate_id,
        item_id,
        clarification_followup_text(
            who=who,
            cleared=cleared,
            before_category=item.ai_category,
            after_category=updated.ai_category,
            after_notes=updated.ai_condition_notes,
            confidence=reading.ai_classification_confidence,
            failed=failed,
        ),
    )

    return Clarification(
        item=updated,
        answer=posted,
        reply=reply,
        cleared=cleared,
        confidence=reading.ai_classification_confidence,
        previous_category=item.ai_category,
        failed=failed,
    )
