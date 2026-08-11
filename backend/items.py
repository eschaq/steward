"""Writing classified items to Firestore.

Item's shape is fixed by docs/estate-agent-data-model.md — this module fills in
exactly those fields and nothing more.
"""

from enum import Enum
from typing import Optional

from classify import Classification, classify_image
from firebase_app import get_db
from models import Item, SuggestedDisposition


def _to_firestore(item: Item) -> dict:
    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in item.model_dump().items()
    }


def create_item_from_classification(
    estate_id: str,
    classification: Classification,
    photo_urls: Optional[list[str]] = None,
    item_id: Optional[str] = None,
) -> Item:
    """Create the Item document for a freshly classified photo.

    Status comes from the confidence threshold, not from the caller — a
    low-confidence item lands in `needs_clarification` every time.

    suggested_disposition stays `uncertain` for now: per the data model it is
    meant to be weighted by this estate's OverrideLog history, and that loop
    isn't built yet. A one-shot guess here is explicitly what the RDD rejects.
    """
    db = get_db()
    doc_ref = db.collection(Item.COLLECTION).document(item_id) if item_id else (
        db.collection(Item.COLLECTION).document()
    )

    item = Item(
        id=doc_ref.id,
        estate_id=estate_id,
        photo_urls=photo_urls or [],
        ai_category=classification.ai_category,
        ai_condition_notes=classification.ai_condition_notes,
        ai_est_era_or_brand=classification.ai_est_era_or_brand,
        ai_classification_confidence=classification.ai_classification_confidence,
        suggested_disposition=SuggestedDisposition.UNCERTAIN,
        status=classification.status,
    )
    doc_ref.set(_to_firestore(item))
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
