"""End-to-end check of photo classification against the real Gemini API and Firestore.

Not a test suite — a script. Two cases:

  1. test_data/sample_item.png — a real household item. Expect a sensible
     category and confidence at or above the threshold, status `unclaimed`.
  2. A solid-colour square generated here. Expect low confidence and status
     `needs_clarification`, with no invented item.

Both cases write a real Item document under the seed estate.

Usage:
    .venv/bin/python test_classify.py
"""

import sys
from pathlib import Path

from PIL import Image

from classify import CONFIDENCE_THRESHOLD, DEFAULT_MODEL, Classification, status_for_confidence
from firebase_app import PROJECT_ID, get_db
from items import classify_and_create_item
from models import Item, ItemStatus

ESTATE_ID = "seed-estate-001"
BACKEND = Path(__file__).parent
SAMPLE_IMAGE = BACKEND / "test_data" / "sample_item.png"
BLANK_IMAGE = BACKEND / "test_data" / "generated_blank_square.png"

# Fixed ids so re-running overwrites instead of piling up test items.
SAMPLE_ITEM_ID = "test-classify-sample-001"
BLANK_ITEM_ID = "test-classify-blank-001"


def make_blank_square(path: Path) -> Path:
    """A deliberately unrecognizable image: one flat colour, no item in it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (512, 512), (108, 122, 137)).save(path)
    return path


def report(label: str, item: Item, classification) -> None:
    print(f"{label}")
    print(f"  item_id                       {item.id}")
    print(f"  ai_category                   {item.ai_category}")
    print(f"  ai_condition_notes            {item.ai_condition_notes}")
    print(f"  ai_est_era_or_brand           {item.ai_est_era_or_brand}")
    print(f"  ai_classification_confidence  {item.ai_classification_confidence}")
    print(f"  status                        {item.status.value}")
    if classification.error:
        print(f"  classifier error              {classification.error}")


def main() -> int:
    print(f"Project: {PROJECT_ID}")
    print(f"Model:   {DEFAULT_MODEL}")
    print(f"Estate:  {ESTATE_ID}")
    print(f"Threshold: confidence < {CONFIDENCE_THRESHOLD} -> needs_clarification\n")

    failures = []

    # Case 1 — a real photo of a real thing.
    item, classification = classify_and_create_item(
        ESTATE_ID,
        str(SAMPLE_IMAGE),
        photo_urls=[f"file://{SAMPLE_IMAGE}"],
        item_id=SAMPLE_ITEM_ID,
    )
    report(f"sample_item.png", item, classification)
    if classification.error:
        failures.append(f"sample photo: classifier failed — {classification.error}")
    if item.ai_classification_confidence < CONFIDENCE_THRESHOLD:
        failures.append(
            f"sample photo: confidence {item.ai_classification_confidence} "
            f"below threshold, so it routed to {item.status.value}"
        )
    elif item.status is not ItemStatus.UNCLAIMED:
        failures.append(f"sample photo: expected unclaimed, got {item.status.value}")
    if item.ai_category.strip().lower() in ("", "unknown"):
        failures.append(f"sample photo: unusable category {item.ai_category!r}")
    print()

    # Case 2 — nothing recognizable in frame; the agent should ask, not guess.
    make_blank_square(BLANK_IMAGE)
    blank_item, blank_classification = classify_and_create_item(
        ESTATE_ID,
        str(BLANK_IMAGE),
        photo_urls=[f"file://{BLANK_IMAGE}"],
        item_id=BLANK_ITEM_ID,
    )
    report("generated_blank_square.png", blank_item, blank_classification)
    if blank_item.status is not ItemStatus.NEEDS_CLARIFICATION:
        failures.append(
            f"blank square: expected needs_clarification, got {blank_item.status.value} "
            f"at confidence {blank_item.ai_classification_confidence}"
        )
    print()

    # The threshold itself, checked directly rather than inferred from a photo.
    # This is the routing rule, not a stand-in for the API call above.
    print("threshold routing")
    for confidence in (0.0, 0.59, CONFIDENCE_THRESHOLD, 0.95):
        by_value = status_for_confidence(confidence)
        on_model = Classification(
            ai_category="probe", ai_condition_notes="probe", ai_classification_confidence=confidence
        ).status
        expected = (
            ItemStatus.NEEDS_CLARIFICATION
            if confidence < CONFIDENCE_THRESHOLD
            else ItemStatus.UNCLAIMED
        )
        mark = "ok " if by_value is expected is on_model else "FAIL"
        print(f"  {mark} confidence {confidence:<5} -> {by_value.value}")
        if mark == "FAIL":
            failures.append(f"threshold routing wrong at confidence {confidence}")
    print()

    # Read both back so we know Firestore actually holds what we printed.
    db = get_db()
    for item_id in (SAMPLE_ITEM_ID, BLANK_ITEM_ID):
        snapshot = db.collection(Item.COLLECTION).document(item_id).get()
        if not snapshot.exists:
            failures.append(f"items/{item_id} not readable back from Firestore")
            continue
        stored = Item.model_validate(snapshot.to_dict())
        print(f"read back  items/{stored.id}  status={stored.status.value}")

    # Distinguish "the API refused to talk to us" from "our logic is wrong" —
    # otherwise a billing problem reads as a broken classifier.
    api_errors = [c.error for c in (classification, blank_classification) if c.error]
    if len(api_errors) == 2:
        print("\nBLOCKED — the Gemini API rejected both calls, so classification quality")
        print("could not be judged. The failure path itself behaved correctly: both items")
        print("landed in needs_clarification with an honest note instead of a guess.")
        print(f"\n  {api_errors[0]}")
        return 2

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nOK — real photo classified and stored, blank square routed to needs_clarification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
