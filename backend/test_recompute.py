"""End-to-end check that a stale suggestion catches up, against real Firestore.

Not a test suite — a script. It rebuilds the cold/warm scenario from
test_overrides.py and then asks the question that script left open: the item
created before the estate had any history still says `uncertain` — does
`recompute_suggestion` bring it up to date?

  (a) The item created with no `armchair` history stored `uncertain`, still
      stores `uncertain` after four decisions land, and recomputes to `donate` —
      updating the Item document, not just the return value.
  (b) A resolved item is left alone. The same weighting function would say
      `donate` for its category right now, and the stored value stays put.

Idempotent: fixed ids, and this estate's override logs for the category under
test are cleared before the run.

Usage:
    .venv/bin/python test_recompute.py

Exit codes: 0 both cases behaved, 1 a real logic failure, 2 the Gemini API
refused the call so there was no category to build a history for.
"""

import sys

from classify import classify_image
from firebase_app import PROJECT_ID
from items import create_item_from_classification, recompute_suggestion
from membership import accept_invite, create_auth_user, invite_to_estate
from models import ItemStatus, MembershipRole, SuggestedDisposition
from overrides import get_override_history, suggest_disposition
from test_claims import BENEFICIARIES, ESTATE_ID
from test_overrides import (
    HISTORY_DECISIONS,
    HISTORY_ITEM_IDS,
    NEW_ITEM_NO_HISTORY,
    SAMPLE_IMAGE,
    build_decided_item,
    check,
    check_in,
    clear_category_history,
    read_item,
)
from test_resolutions import EXECUTOR

# The item resolved and already decided — case (b) leaves this one alone.
RESOLVED_ITEM = HISTORY_ITEM_IDS[0]


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

    classification = classify_image(str(SAMPLE_IMAGE))
    if classification.error:
        print(f"\nBLOCKED — the Gemini API refused the call: {classification.error}")
        print("There is no real category to build a history for, so the recompute")
        print("could not be exercised. This is billing/quota, not logic.")
        return 2

    category = classification.ai_category
    print(f"  classified   {SAMPLE_IMAGE.name} -> {category!r}")

    cleared = clear_category_history(category)
    if cleared:
        print(f"  cleaned      {cleared} override log(s) in {category!r}")
    check(failures, "history starts empty", len(get_override_history(ESTATE_ID, category)), 0)
    print()

    # --- the item is created cold ------------------------------------------
    print(f"(a) {NEW_ITEM_NO_HISTORY} — created before the estate had a habit")
    create_item_from_classification(
        ESTATE_ID, classification, item_id=NEW_ITEM_NO_HISTORY
    )
    check(
        failures, "stored at creation",
        read_item(NEW_ITEM_NO_HISTORY).suggested_disposition,
        SuggestedDisposition.UNCERTAIN,
    )

    for item_id, choice in zip(HISTORY_ITEM_IDS, HISTORY_DECISIONS):
        build_decided_item(item_id, category, beneficiary_uid, executor_uid, choice)
    print(f"  ...4 {category!r} items decided: "
          f"{', '.join(c.value for c in HISTORY_DECISIONS)}")

    # The snapshot problem, stated as an assertion: the history moved, the item
    # did not.
    check(
        failures, "still stale before recompute",
        read_item(NEW_ITEM_NO_HISTORY).suggested_disposition,
        SuggestedDisposition.UNCERTAIN,
    )

    updated = recompute_suggestion(NEW_ITEM_NO_HISTORY)
    print(f"  reason: {updated.reason}")
    check(failures, "returned", updated.suggested_disposition, SuggestedDisposition.DONATE)
    check(failures, "has_pattern", updated.has_pattern, True)
    check(failures, "matching_count", updated.matching_count, 3)
    check(failures, "history_count", updated.history_count, 4)
    check_in(failures, "reason gives the tally", "3 of 4", updated.reason)
    # The point of the exercise: the document moved, not just the return value.
    check(
        failures, "stored after recompute",
        read_item(NEW_ITEM_NO_HISTORY).suggested_disposition,
        SuggestedDisposition.DONATE,
    )
    # Status is untouched — this changes advice, not where the item is in the flow.
    check(
        failures, "status untouched",
        read_item(NEW_ITEM_NO_HISTORY).status, ItemStatus.UNCLAIMED,
    )

    again = recompute_suggestion(NEW_ITEM_NO_HISTORY)
    check(failures, "second call is stable", again.suggested_disposition,
          SuggestedDisposition.DONATE)
    print()

    # --- (b) a resolved item is left alone ---------------------------------
    print(f"(b) {RESOLVED_ITEM} — already resolved and decided")
    before = read_item(RESOLVED_ITEM)
    check(failures, "status", before.status, ItemStatus.RESOLVED)
    check(failures, "stored suggestion", before.suggested_disposition,
          SuggestedDisposition.UNCERTAIN)

    # Not a vacuous check: the weighting function would say donate for this
    # category right now, so the guard is what keeps the stored value put.
    would_be = suggest_disposition(ESTATE_ID, category)
    check(failures, "what it would say if recomputed", would_be.suggested_disposition,
          SuggestedDisposition.DONATE)

    noop = recompute_suggestion(RESOLVED_ITEM)
    print(f"  reason: {noop.reason}")
    check(failures, "returned", noop.suggested_disposition, before.suggested_disposition)
    check(failures, "has_pattern", noop.has_pattern, False)
    check_in(failures, "reason says why", "resolved", noop.reason)

    after = read_item(RESOLVED_ITEM)
    check(failures, "stored suggestion untouched", after.suggested_disposition,
          before.suggested_disposition)
    check(failures, "status untouched", after.status, before.status)
    print()

    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("OK — the stale item caught up, and the resolved one was left alone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
