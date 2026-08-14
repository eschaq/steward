"""Writing classified items to Firestore.

Item's shape is fixed by docs/estate-agent-data-model.md — this module fills in
exactly those fields and nothing more.
"""

from enum import Enum
from typing import Optional

from google.cloud.firestore_v1 import ArrayUnion
from google.cloud.firestore_v1.base_query import FieldFilter

from classify import Classification, classify_image
from firebase_app import get_db
from messages import post_clarifying_question
from models import Item, ItemStatus, SuggestedDisposition
from overrides import DispositionSuggestion, suggest_disposition


# Statuses where a suggestion is still worth anything. A `resolved` item's
# disposition has already been decided by a person, and `routed` is further along
# still — reaching back to change what the agent suggests would be rewriting
# advice nobody is waiting on. `needs_clarification` is excluded for the opposite
# reason: the agent doesn't yet know what the item is.
SUGGESTION_ELIGIBLE_STATUSES = frozenset(
    {ItemStatus.UNCLAIMED, ItemStatus.CLAIMED, ItemStatus.CONTESTED}
)


class ItemError(Exception):
    """The item asked about doesn't exist."""


def _to_firestore(item: Item) -> dict:
    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in item.model_dump().items()
    }


def suggestion_for(
    estate_id: str, classification: Classification
) -> DispositionSuggestion:
    """The disposition the agent would suggest for this classification, and why.

    Exposed separately because `Item` has no field for the reason — its shape is
    fixed by the data model doc — so a caller that wants to show the family *why*
    ("this estate has donated 3 of 4 kitchenware items") asks for it here.
    """
    return suggest_disposition(
        estate_id=estate_id,
        item_category=classification.ai_category,
        baseline=SuggestedDisposition.UNCERTAIN,
        ai_classification_confidence=classification.ai_classification_confidence,
        identified=not classification.needs_clarification,
    )


def get_item(item_id: str) -> Optional[Item]:
    """One item, or None if there is no such document."""
    snapshot = get_db().collection(Item.COLLECTION).document(item_id).get()
    if not snapshot.exists:
        return None
    return Item.model_validate(snapshot.to_dict())


def add_photo_url(item_id: str, url: str) -> Item:
    """Append one photograph's URL to an item and return the updated item.

    ArrayUnion rather than read-modify-write: two executors adding photos at the
    same moment should end up with both, not with one silently overwriting the
    other. The Claim collection makes the same choice for the same reason.
    """
    doc_ref = get_db().collection(Item.COLLECTION).document(item_id)
    if not doc_ref.get().exists:
        raise ItemError(f"No item {item_id} to attach a photo to.")

    doc_ref.update({"photo_urls": ArrayUnion([url])})
    return Item.model_validate(doc_ref.get().to_dict())


def list_items_for_estate(estate_id: str) -> list[Item]:
    """Every item in an estate, newest first — what the dashboard renders.

    Single-field equality filter, so Firestore's automatic index covers it.
    Ordering is done here rather than in the query for the same reason: an
    order_by on a second field would want a composite index.
    """
    snapshots = (
        get_db()
        .collection(Item.COLLECTION)
        .where(filter=FieldFilter("estate_id", "==", estate_id))
        .get()
    )
    items = [Item.model_validate(s.to_dict()) for s in snapshots]
    return sorted(items, key=lambda i: i.created_at, reverse=True)


def recompute_suggestion(item_id: str) -> DispositionSuggestion:
    """Re-derive an item's suggested_disposition from the estate's history now.

    The suggestion written at classification time is a snapshot: it reflects the
    override history as it stood that day, and later decisions in the same
    category never reached it. This re-runs the same weighting function against
    the current history and writes the result back if it moved.

    Items outside SUGGESTION_ELIGIBLE_STATUSES are a no-op, not an error — the
    stored value is returned untouched, with a reason saying why it was left
    alone.

    The baseline is `uncertain`, deliberately, rather than whatever is currently
    stored. That means the suggestion always reflects the history as it stands:
    if the pattern that produced `donate` later evens out, this walks the item
    back to `uncertain` instead of leaving a lean nothing supports any more.
    """
    doc_ref = get_db().collection(Item.COLLECTION).document(item_id)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        raise ItemError(f"No item {item_id} to recompute a suggestion for.")

    item = Item.model_validate(snapshot.to_dict())

    if item.status not in SUGGESTION_ELIGIBLE_STATUSES:
        return DispositionSuggestion(
            suggested_disposition=item.suggested_disposition,
            reason=(
                f"This item is {item.status.value}, so its disposition isn't the "
                "agent's to suggest any more — leaving it as it is."
            ),
            has_pattern=False,
            ai_classification_confidence=item.ai_classification_confidence,
        )

    # An eligible status is itself the evidence the item is identified: classify
    # routes anything below the confidence threshold to `needs_clarification`,
    # which is excluded above. The stored confidence is the classifier's original
    # read and can be stale by now; the status is current.
    suggestion = suggest_disposition(
        estate_id=item.estate_id,
        item_category=item.ai_category,
        baseline=SuggestedDisposition.UNCERTAIN,
        ai_classification_confidence=item.ai_classification_confidence,
        identified=True,
    )

    if suggestion.suggested_disposition is not item.suggested_disposition:
        doc_ref.update({"suggested_disposition": suggestion.suggested_disposition.value})

    return suggestion


def create_item_from_classification(
    estate_id: str,
    classification: Classification,
    photo_urls: Optional[list[str]] = None,
    item_id: Optional[str] = None,
) -> Item:
    """Create the Item document for a freshly classified photo.

    Status comes from the confidence threshold, not from the caller — a
    low-confidence item lands in `needs_clarification` every time.

    suggested_disposition is weighted by this estate's OverrideLog history for
    the item's category. With no history it stays `uncertain` — the classifier
    reads what a thing *is*, not what should happen to it, and a one-shot guess
    at the latter is what the RDD rejects.

    An item that lands in `needs_clarification` gets the agent's clarifying
    question posted to the Message Center — the status alone is a dead end for
    the family, since nothing tells them the agent wants a hand.
    """
    db = get_db()
    doc_ref = db.collection(Item.COLLECTION).document(item_id) if item_id else (
        db.collection(Item.COLLECTION).document()
    )

    suggestion = suggestion_for(estate_id, classification)

    item = Item(
        id=doc_ref.id,
        estate_id=estate_id,
        photo_urls=photo_urls or [],
        ai_category=classification.ai_category,
        ai_condition_notes=classification.ai_condition_notes,
        ai_est_era_or_brand=classification.ai_est_era_or_brand,
        ai_classification_confidence=classification.ai_classification_confidence,
        suggested_disposition=suggestion.suggested_disposition,
        status=classification.status,
    )
    doc_ref.set(_to_firestore(item))

    if item.status is ItemStatus.NEEDS_CLARIFICATION:
        post_clarifying_question(
            estate_id=item.estate_id,
            item_id=item.id,
            ai_category=item.ai_category,
            ai_condition_notes=item.ai_condition_notes,
        )

    return item


def classify_and_create_item(
    estate_id: str,
    image_path: str,
    photo_urls: Optional[list[str]] = None,
    item_id: Optional[str] = None,
) -> tuple[Item, Classification]:
    """Classify a photo and persist the resulting Item in one step."""
    classification = classify_image(image_path)
    item = create_item_from_classification(
        estate_id, classification, photo_urls=photo_urls, item_id=item_id
    )
    return item, classification
