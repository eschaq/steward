"""End-to-end check of claim recording and status recomputation against the real project.

Not a test suite — a script. It creates two items under the seed estate, has one
beneficiary claim item A (expects `claimed`), has two different beneficiaries
claim item B (expects `contested`), and checks the claim counts queried back by
item_id. It also re-claims item A as the same user to show that a repeat claim is
recorded but does not escalate the item to `contested`.

Idempotent: fixed item ids and fixed test emails, and any claims left by a
previous run are deleted before the run starts.

Usage:
    .venv/bin/python test_claims.py
"""

import sys
from datetime import datetime, timezone

from google.cloud.firestore_v1.base_query import FieldFilter

from claims import (
    ClaimError,
    count_claims,
    count_distinct_claimants,
    get_claims_for_item,
    record_claim,
)
from firebase_app import PROJECT_ID, get_db
from init_firestore import to_firestore
from membership import accept_invite, create_auth_user, invite_to_estate
from models import Claim, Item, ItemStatus, MembershipRole, SuggestedDisposition


from test_guard import require_destructive_ok

require_destructive_ok(__name__, "test_claims.py", "test-claim-item-a and -b, and every claim on them")

ESTATE_ID = "seed-estate-001"

ITEM_A_ID = "test-claim-item-a"
ITEM_B_ID = "test-claim-item-b"

BENEFICIARIES = [
    ("steward-test-beneficiary@example.com", "Test Beneficiary"),
    ("steward-test-beneficiary-2@example.com", "Test Beneficiary Two"),
]


def reset_item(item_id: str, category: str, notes: str) -> None:
    """(Re)create the item as `unclaimed` and delete any claims left on it."""
    db = get_db()
    item = Item(
        id=item_id,
        estate_id=ESTATE_ID,
        photo_urls=[],
        ai_category=category,
        ai_condition_notes=notes,
        ai_est_era_or_brand=None,
        ai_classification_confidence=0.9,
        suggested_disposition=SuggestedDisposition.UNCERTAIN,
        status=ItemStatus.UNCLAIMED,
        created_at=datetime.now(timezone.utc),
    )
    db.collection(Item.COLLECTION).document(item_id).set(to_firestore(item))

    stale = (
        db.collection(Claim.COLLECTION)
        .where(filter=FieldFilter("item_id", "==", item_id))
        .get()
    )
    for snapshot in stale:
        snapshot.reference.delete()
    if stale:
        print(f"  cleaned  {len(stale)} claim(s) from a previous run on {item_id}")


def read_status(item_id: str) -> ItemStatus:
    """Item status read straight back out of Firestore, not from a return value."""
    snapshot = get_db().collection(Item.COLLECTION).document(item_id).get()
    return ItemStatus(snapshot.to_dict()["status"])


def check(failures: list[str], label: str, actual, expected) -> None:
    actual_s = actual.value if isinstance(actual, ItemStatus) else actual
    expected_s = expected.value if isinstance(expected, ItemStatus) else expected
    if actual == expected:
        print(f"  ok       {label}: {actual_s}")
    else:
        failures.append(f"{label}: got {actual_s}, expected {expected_s}")
        print(f"  FAIL     {label}: got {actual_s}, expected {expected_s}")


def main() -> int:
    print(f"Project: {PROJECT_ID}")
    print(f"Estate:  {ESTATE_ID}\n")

    failures: list[str] = []

    print("setup")
    uids = []
    for email, display_name in BENEFICIARIES:
        uid = create_auth_user(email, display_name)
        invite_to_estate(ESTATE_ID, email, MembershipRole.BENEFICIARY)
        accept_invite(ESTATE_ID, uid)
        uids.append(uid)
        print(f"  beneficiary  {email}  uid={uid}")
    uid_one, uid_two = uids

    reset_item(ITEM_A_ID, "kitchenware", "Set of six tumblers, no chips.")
    reset_item(ITEM_B_ID, "furniture", "Walnut side table, ring mark on top.")
    print(f"  items        {ITEM_A_ID}, {ITEM_B_ID} (both unclaimed)\n")

    # Item A — a single beneficiary claims it.
    print(f"item A ({ITEM_A_ID}) — one claimant")
    claim_a, status_a = record_claim(ITEM_A_ID, uid_one, comment="Grandma promised me these.")
    check(failures, "returned status", status_a, ItemStatus.CLAIMED)
    check(failures, "status in Firestore", read_status(ITEM_A_ID), ItemStatus.CLAIMED)
    check(failures, "claims by item_id", count_claims(ITEM_A_ID), 1)
    check(failures, "distinct claimants", count_distinct_claimants(ITEM_A_ID), 1)
    check(failures, "comment persisted", get_claims_for_item(ITEM_A_ID)[0].comment,
          "Grandma promised me these.")
    print(f"           claim id={claim_a.id}\n")

    # Item B — two different beneficiaries claim it.
    print(f"item B ({ITEM_B_ID}) — two claimants")
    _, status_first = record_claim(ITEM_B_ID, uid_one)
    check(failures, "status after 1st claim", status_first, ItemStatus.CLAIMED)

    _, status_second = record_claim(ITEM_B_ID, uid_two, comment="This was in my room growing up.")
    check(failures, "returned status", status_second, ItemStatus.CONTESTED)
    check(failures, "status in Firestore", read_status(ITEM_B_ID), ItemStatus.CONTESTED)
    check(failures, "claims by item_id", count_claims(ITEM_B_ID), 2)
    check(failures, "distinct claimants", count_distinct_claimants(ITEM_B_ID), 2)
    claimants = {c.user_id for c in get_claims_for_item(ITEM_B_ID)}
    check(failures, "both claimants recorded", claimants == {uid_one, uid_two}, True)
    print()

    # Repeat claim from a user who already claimed item A: recorded (no dedup),
    # but one person is still one claimant, so item A stays `claimed`.
    print(f"item A — same beneficiary claims again")
    _, status_repeat = record_claim(ITEM_A_ID, uid_one, comment="Still hoping for these.")
    check(failures, "claims by item_id", count_claims(ITEM_A_ID), 2)
    check(failures, "distinct claimants", count_distinct_claimants(ITEM_A_ID), 1)
    check(failures, "status stays", status_repeat, ItemStatus.CLAIMED)
    check(failures, "status in Firestore", read_status(ITEM_A_ID), ItemStatus.CLAIMED)
    print()

    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("OK — claimed and contested transitions both verified against Firestore.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ClaimError as exc:
        print(f"\nClaimError: {exc}")
        sys.exit(1)
