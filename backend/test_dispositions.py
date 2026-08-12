"""End-to-end check of disposition decisions against real Firestore.

Not a test suite — a script. Four cases, all against the live project:

  (a) A real decision (donate) on a resolved item writes both documents, and
      they agree with each other and with the item.
  (b) `uncertain` is refused, with nothing written to either collection.
  (c) An item that isn't resolved yet is refused by the same status check the
      last loop added, again with nothing written.
  (d) The channel map: donate -> donate, sell -> sell_marketplace, and no Tier 1
      path to sell_auction_bulk.

Idempotent: fixed ids, and any documents left by a previous run are cleared
before the run starts, so "nothing written" means this run wrote nothing.

Usage:
    .venv/bin/python test_dispositions.py
"""

import sys

from claims import record_claim
from dispositions import (
    CHANNEL_FOR_CHOICE,
    DispositionError,
    disposition_id,
    get_disposition,
    get_disposition_decision,
    record_disposition_decision,
)
from firebase_app import PROJECT_ID, get_db
from membership import accept_invite, create_auth_user, invite_to_estate
from models import (
    Disposition,
    DispositionChannel,
    DispositionStatus,
    Item,
    ItemStatus,
    MembershipRole,
    OverrideLog,
    ResolutionType,
    SuggestedDisposition,
)
from overrides import override_log_id
from resolutions import resolve_item
from test_claims import BENEFICIARIES, ESTATE_ID, reset_item
from test_resolutions import EXECUTOR, clear_resolution

CATEGORY = "test-disposition-category"

ITEM_DONATE = "test-disposition-donate"
ITEM_SELL = "test-disposition-sell"
ITEM_UNCERTAIN = "test-disposition-uncertain"
ITEM_UNRESOLVED = "test-disposition-unresolved"

ALL_ITEMS = [ITEM_DONATE, ITEM_SELL, ITEM_UNCERTAIN, ITEM_UNRESOLVED]


def clear_decision(item_id: str) -> None:
    """Drop both documents a decision writes, so this run starts from nothing."""
    db = get_db()
    db.collection(OverrideLog.COLLECTION).document(override_log_id(item_id)).delete()
    db.collection(Disposition.COLLECTION).document(disposition_id(item_id)).delete()


def read_item(item_id: str) -> Item:
    return Item.model_validate(
        get_db().collection(Item.COLLECTION).document(item_id).get().to_dict()
    )


def check(failures: list[str], label: str, actual, expected) -> None:
    def show(value):
        return value.value if hasattr(value, "value") else value

    if actual == expected:
        print(f"  ok       {label}: {show(actual)}")
    else:
        failures.append(f"{label}: got {show(actual)}, expected {show(expected)}")
        print(f"  FAIL     {label}: got {show(actual)}, expected {show(expected)}")


def check_nothing_written(failures: list[str], item_id: str) -> None:
    """Refused has to mean nothing happened, in both collections."""
    check(failures, "no override log", get_disposition_decision(item_id), None)
    check(failures, "no disposition", get_disposition(item_id), None)


def make_resolved_item(item_id: str, claimant_uid: str, executor_uid: str) -> None:
    """Take an item as far as `resolved`, ready for a disposition decision."""
    reset_item(item_id, CATEGORY, "Seeded for the disposition test.")
    clear_resolution(item_id)
    clear_decision(item_id)
    record_claim(item_id, claimant_uid)
    resolve_item(
        item_id,
        resolved_by_user_id=executor_uid,
        resolution_type=ResolutionType.ASSIGNED_TO_CLAIMANT,
        resolved_to_user_id=claimant_uid,
        notes="Seeded for the disposition test.",
    )


def main() -> int:
    print(f"Project: {PROJECT_ID}")
    print(f"Estate:  {ESTATE_ID}\n")

    failures: list[str] = []

    # --- setup -------------------------------------------------------------
    print("setup")
    executor_uid = create_auth_user(*EXECUTOR)
    invite_to_estate(ESTATE_ID, EXECUTOR[0], MembershipRole.EXECUTOR)
    accept_invite(ESTATE_ID, executor_uid)

    beneficiary_email, beneficiary_name = BENEFICIARIES[0]
    beneficiary_uid = create_auth_user(beneficiary_email, beneficiary_name)
    invite_to_estate(ESTATE_ID, beneficiary_email, MembershipRole.BENEFICIARY)
    accept_invite(ESTATE_ID, beneficiary_uid)
    print(f"  executor     uid={executor_uid}")
    print(f"  beneficiary  uid={beneficiary_uid}")

    for item_id in (ITEM_DONATE, ITEM_SELL, ITEM_UNCERTAIN):
        make_resolved_item(item_id, beneficiary_uid, executor_uid)
    print(f"  resolved     {ITEM_DONATE}, {ITEM_SELL}, {ITEM_UNCERTAIN}")

    # Left unclaimed on purpose, for case (c).
    reset_item(ITEM_UNRESOLVED, CATEGORY, "Never claimed, never resolved.")
    clear_decision(ITEM_UNRESOLVED)
    print(f"  unclaimed    {ITEM_UNRESOLVED}")

    # Every item starts with neither document, so "nothing written" below is a
    # statement about this run and not about a tidy previous one.
    leftover = [
        item_id
        for item_id in ALL_ITEMS
        if get_disposition_decision(item_id) or get_disposition(item_id)
    ]
    check(failures, "all items start undecided", leftover, [])
    print()

    # --- (a) a real decision writes both documents -------------------------
    print(f"(a) executor decides donate on {ITEM_DONATE}")
    entry, disposition = record_disposition_decision(
        ITEM_DONATE, SuggestedDisposition.DONATE, executor_uid
    )
    print(f"  override log id  {entry.id}")
    print(f"  disposition id   {disposition.id}")

    # Read both back rather than trusting the returned objects.
    stored_log = get_disposition_decision(ITEM_DONATE)
    stored_disposition = get_disposition(ITEM_DONATE)

    if stored_log is None or stored_disposition is None:
        failures.append("one of the two documents was not readable back")
        print("  FAIL     one of the two documents was not readable back")
    else:
        item = read_item(ITEM_DONATE)
        print("  override log")
        check(failures, "    item_id", stored_log.item_id, ITEM_DONATE)
        check(failures, "    estate_id", stored_log.estate_id, ESTATE_ID)
        check(failures, "    item_category", stored_log.item_category, item.ai_category)
        check(
            failures, "    ai_suggested_disposition",
            stored_log.ai_suggested_disposition, item.suggested_disposition,
        )
        check(
            failures, "    executor_chosen_disposition",
            stored_log.executor_chosen_disposition, SuggestedDisposition.DONATE,
        )
        print("  disposition")
        check(failures, "    item_id", stored_disposition.item_id, ITEM_DONATE)
        check(failures, "    channel", stored_disposition.channel, DispositionChannel.DONATE)
        check(failures, "    status", stored_disposition.status, DispositionStatus.PENDING)
        check(failures, "    completed_at", stored_disposition.completed_at, None)
        print("  consistency")
        check(
            failures, "    both name the same item",
            stored_log.item_id, stored_disposition.item_id,
        )
        check(
            failures, "    channel matches the logged choice",
            stored_disposition.channel,
            CHANNEL_FOR_CHOICE[stored_log.executor_chosen_disposition],
        )
        # The decision routes the item; it does not re-open or advance it.
        check(failures, "    item still resolved", item.status, ItemStatus.RESOLVED)
    print()

    # --- (b) uncertain is not a decision -----------------------------------
    print(f"(b) executor tries uncertain on {ITEM_UNCERTAIN}")
    try:
        record_disposition_decision(
            ITEM_UNCERTAIN, SuggestedDisposition.UNCERTAIN, executor_uid
        )
        failures.append("'uncertain' was accepted as a disposition decision")
        print("  FAIL     'uncertain' was accepted")
    except DispositionError as exc:
        print(f"  ok       refused: {exc}")
    check_nothing_written(failures, ITEM_UNCERTAIN)
    print()

    # --- (c) the item has to be resolved first -----------------------------
    print(f"(c) executor tries donate on the unresolved {ITEM_UNRESOLVED}")
    check(failures, "item status", read_item(ITEM_UNRESOLVED).status, ItemStatus.UNCLAIMED)
    try:
        record_disposition_decision(
            ITEM_UNRESOLVED, SuggestedDisposition.DONATE, executor_uid
        )
        failures.append("an unresolved item accepted a disposition decision")
        print("  FAIL     unresolved item accepted a decision")
    except DispositionError as exc:
        print(f"  ok       refused: {exc}")
    check_nothing_written(failures, ITEM_UNRESOLVED)
    print()

    # --- (d) the channel map -----------------------------------------------
    print("(d) channel mapping")
    _, sell_disposition = record_disposition_decision(
        ITEM_SELL, SuggestedDisposition.SELL, executor_uid
    )
    check(
        failures, "sell routes to", sell_disposition.channel,
        DispositionChannel.SELL_MARKETPLACE,
    )
    check(
        failures, "read back from Firestore", get_disposition(ITEM_SELL).channel,
        DispositionChannel.SELL_MARKETPLACE,
    )
    check(
        failures, "discard routes to", CHANNEL_FOR_CHOICE[SuggestedDisposition.DISCARD],
        DispositionChannel.DISCARD,
    )
    # Tier 3 is on the enum so the entity's shape never changes, but nothing in
    # Tier 1 may route to it.
    check(
        failures, "no Tier 1 path to sell_auction_bulk",
        DispositionChannel.SELL_AUCTION_BULK in CHANNEL_FOR_CHOICE.values(), False,
    )
    check(failures, "uncertain has no channel",
          SuggestedDisposition.UNCERTAIN in CHANNEL_FOR_CHOICE, False)
    print()

    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("OK — decision writes both documents, uncertain refused, unresolved refused.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
