"""Initialize the Tier 1 Firestore collections and seed one document in each.

Verifies read/write against the real project. Safe to re-run: seed documents use
fixed ids, so a second run overwrites rather than duplicating.

Usage:
    python init_firestore.py
"""

import os
import sys
from datetime import datetime, timezone
from enum import Enum

import firebase_admin
from firebase_admin import credentials, firestore

from models import (
    Estate,
    EstateMembership,
    EstateStatus,
    Item,
    ItemStatus,
    MembershipRole,
    RoleType,
    SuggestedDisposition,
    User,
)

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "steward-hackathon-505217")

SEED_ESTATE_ID = "seed-estate-001"
SEED_USER_ID = "seed-user-001"
SEED_MEMBERSHIP_ID = "seed-membership-001"
SEED_ITEM_ID = "seed-item-001"


def to_firestore(model) -> dict:
    """Model to a Firestore-writable dict: enums become their string values,
    datetimes stay native so they land as real Firestore timestamps."""
    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in model.model_dump().items()
    }


def build_seed_documents():
    now = datetime.now(timezone.utc)

    user = User(
        id=SEED_USER_ID,
        email="executor@example.com",
        display_name="Seed Executor",
        role_type=RoleType.HUMAN,
        created_at=now,
    )
    estate = Estate(
        id=SEED_ESTATE_ID,
        name="Seed Estate",
        executor_user_id=user.id,
        status=EstateStatus.ACTIVE,
        created_at=now,
    )
    membership = EstateMembership(
        id=SEED_MEMBERSHIP_ID,
        estate_id=estate.id,
        user_id=user.id,
        role=MembershipRole.EXECUTOR,
        invited_at=now,
        accepted_at=now,
    )
    item = Item(
        id=SEED_ITEM_ID,
        estate_id=estate.id,
        photo_urls=["gs://steward-seed/example-item.jpg"],
        ai_category="kitchenware",
        ai_condition_notes="Light wear on the rim, no chips.",
        ai_est_era_or_brand="mid-century, unmarked",
        ai_classification_confidence=0.82,
        suggested_disposition=SuggestedDisposition.DONATE,
        status=ItemStatus.UNCLAIMED,
        created_at=now,
    )
    return [user, estate, membership, item]


def main() -> int:
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.ApplicationDefault(), {"projectId": PROJECT_ID}
        )
    db = firestore.client()

    print(f"Project: {PROJECT_ID}\n")

    documents = build_seed_documents()

    for model in documents:
        collection = type(model).COLLECTION
        db.collection(collection).document(model.id).set(to_firestore(model))
        print(f"  wrote  {collection}/{model.id}")

    print()

    failures = []
    for model in documents:
        collection = type(model).COLLECTION
        snapshot = db.collection(collection).document(model.id).get()
        if not snapshot.exists:
            failures.append(f"{collection}/{model.id}")
            print(f"  FAIL   {collection}/{model.id} not readable")
            continue
        # Re-validate through the model so a schema drift surfaces here, not later.
        type(model).model_validate(snapshot.to_dict())
        print(f"  read   {collection}/{model.id}")

    if failures:
        print(f"\n{len(failures)} document(s) failed read-back: {', '.join(failures)}")
        return 1

    print(f"\nOK — {len(documents)} collections initialized and verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
