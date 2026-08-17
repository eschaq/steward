"""End-to-end check of item resolution against real Firestore.

Not a test suite — a script. Three cases, all against the live project:

  (a) A beneficiary tries to resolve the contested item and is refused —
      `require_role` rejects it and nothing is written.
  (b) The executor resolves the same item with `rotation`; the item flips to
      `resolved` and the Resolution document holds the right fields.
  (c) Resolving a still-unclaimed item raises instead of quietly succeeding,
      and leaves the item where it was.

Idempotent: fixed ids, and any claims, messages, or resolutions left by a
previous run are cleared before the run starts.

Usage:
    .venv/bin/python test_resolutions.py
"""

import sys

from claims import record_claim
from firebase_app import PROJECT_ID, get_db
from membership import MembershipError, accept_invite, create_auth_user, invite_to_estate
from models import Item, ItemStatus, MembershipRole, Resolution, ResolutionType
from resolutions import ResolutionError, get_resolution, resolution_id, resolve_item
from test_claims import BENEFICIARIES, ESTATE_ID, ITEM_B_ID, reset_item
from test_messages import clear_messages


from test_guard import require_destructive_ok

require_destructive_ok(__name__, "test_resolutions.py", "test-resolve-unclaimed and the claim fixtures it shares")

EXECUTOR = ("steward-test-executor@example.com", "Test Executor")

# A fresh item nobody claims, for case (c).
UNCLAIMED_ITEM_ID = "test-resolve-unclaimed"


def clear_resolution(item_id: str) -> None:
    get_db().collection(Resolution.COLLECTION).document(resolution_id(item_id)).delete()


def read_status(item_id: str) -> ItemStatus:
    """Item status read straight back out of Firestore."""
    snapshot = get_db().collection(Item.COLLECTION).document(item_id).get()
    return ItemStatus(snapshot.to_dict()["status"])


def check(failures: list[str], label: str, actual, expected) -> None:
    def show(value):
        return value.value if hasattr(value, "value") else value

    if actual == expected:
        print(f"  ok       {label}: {show(actual)}")
    else:
        failures.append(f"{label}: got {show(actual)}, expected {show(expected)}")
        print(f"  FAIL     {label}: got {show(actual)}, expected {show(expected)}")


def main() -> int:
    print(f"Project: {PROJECT_ID}")
    print(f"Estate:  {ESTATE_ID}\n")

    failures: list[str] = []

    # --- setup -------------------------------------------------------------
    print("setup")
    executor_uid = create_auth_user(*EXECUTOR)
    invite_to_estate(ESTATE_ID, EXECUTOR[0], MembershipRole.EXECUTOR)
    accept_invite(ESTATE_ID, executor_uid)
    print(f"  executor     {EXECUTOR[0]}  uid={executor_uid}")

    beneficiary_uids = []
    for email, display_name in BENEFICIARIES:
        uid = create_auth_user(email, display_name)
        invite_to_estate(ESTATE_ID, email, MembershipRole.BENEFICIARY)
        accept_invite(ESTATE_ID, uid)
        beneficiary_uids.append(uid)
        print(f"  beneficiary  {email}  uid={uid}")
    uid_one, uid_two = beneficiary_uids

    # The contested item, rebuilt from scratch so this run resolves its own work.
    reset_item(ITEM_B_ID, "furniture", "Walnut side table, ring mark on top.")
    clear_messages(ITEM_B_ID)
    clear_resolution(ITEM_B_ID)
    record_claim(ITEM_B_ID, uid_one)
    record_claim(ITEM_B_ID, uid_two, comment="This was in my room growing up.")
    check(failures, "contested item ready", read_status(ITEM_B_ID), ItemStatus.CONTESTED)

    # An item nobody has claimed, for case (c).
    reset_item(UNCLAIMED_ITEM_ID, "linens", "Boxed tablecloths, unopened.")
    clear_resolution(UNCLAIMED_ITEM_ID)
    check(
        failures, "unclaimed item ready", read_status(UNCLAIMED_ITEM_ID),
        ItemStatus.UNCLAIMED,
    )
    print()

    # --- (a) a beneficiary may not resolve ---------------------------------
    print("(a) beneficiary tries to resolve the contested item")
    try:
        resolve_item(
            ITEM_B_ID,
            resolved_by_user_id=uid_one,
            resolution_type=ResolutionType.ASSIGNED_TO_CLAIMANT,
            resolved_to_user_id=uid_one,
            notes="I'd like to keep it.",
        )
        failures.append("beneficiary was allowed to resolve a contested item")
        print("  FAIL     no error raised — the beneficiary resolved it")
    except MembershipError as exc:
        print(f"  ok       refused: {exc}")

    # Refused has to mean nothing happened, not "errored after writing".
    check(failures, "no resolution written", get_resolution(ITEM_B_ID), None)
    check(failures, "item still contested", read_status(ITEM_B_ID), ItemStatus.CONTESTED)
    print()

    # --- (b) the executor resolves it --------------------------------------
    print("(b) executor resolves it as a rotation")
    resolution = resolve_item(
        ITEM_B_ID,
        resolved_by_user_id=executor_uid,
        resolution_type=ResolutionType.ROTATION,
        resolved_to_user_id=uid_one,
        notes="Two years at Ana's, then two at Sam's. Revisit after that.",
    )
    print(f"  resolution id  {resolution.id}")
    check(failures, "item status", read_status(ITEM_B_ID), ItemStatus.RESOLVED)

    # Read the document back rather than trusting the returned object.
    stored = get_resolution(ITEM_B_ID)
    if stored is None:
        failures.append("resolution document not readable back from Firestore")
        print("  FAIL     resolution document not readable back")
    else:
        check(failures, "item_id", stored.item_id, ITEM_B_ID)
        check(failures, "resolved_by_user_id", stored.resolved_by_user_id, executor_uid)
        check(failures, "resolution_type", stored.resolution_type, ResolutionType.ROTATION)
        check(failures, "resolved_to_user_id", stored.resolved_to_user_id, uid_one)
        check(failures, "notes", stored.notes, resolution.notes)
        check(failures, "resolved_at set", stored.resolved_at is not None, True)

    # Resolved is past the claim triad — a second resolution is refused too.
    try:
        resolve_item(
            ITEM_B_ID,
            resolved_by_user_id=executor_uid,
            resolution_type=ResolutionType.EXECUTOR_OVERRIDE,
            notes="Changed my mind.",
        )
        failures.append("an already-resolved item was resolved a second time")
        print("  FAIL     already-resolved item accepted a second resolution")
    except ResolutionError as exc:
        print(f"  ok       second resolution refused: {exc}")
    print()

    # --- (c) an unclaimed item has nothing to resolve ----------------------
    print("(c) executor tries to resolve a still-unclaimed item")
    try:
        resolve_item(
            UNCLAIMED_ITEM_ID,
            resolved_by_user_id=executor_uid,
            resolution_type=ResolutionType.EXECUTOR_OVERRIDE,
            notes="Sending these to the donation pile.",
        )
        failures.append("an unclaimed item was resolved")
        print("  FAIL     no error raised — the unclaimed item was resolved")
    except ResolutionError as exc:
        print(f"  ok       refused: {exc}")

    check(failures, "no resolution written", get_resolution(UNCLAIMED_ITEM_ID), None)
    check(
        failures, "item still unclaimed", read_status(UNCLAIMED_ITEM_ID),
        ItemStatus.UNCLAIMED,
    )
    print()

    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("OK — beneficiary refused, executor resolved, unclaimed item refused.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
