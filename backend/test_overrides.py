"""End-to-end check of the adaptive suggestion loop against real Firestore.

Not a test suite — a script. It classifies one real photo, then runs the *same*
classification through the suggestion path twice: once with no history for that
category, and once after the executor has decided four similar items. Same input,
different output — which is the whole point of the mechanic.

  (a) No history for the category -> suggested_disposition stays `uncertain`,
      with an explicit "no pattern yet for this estate" signal.
  (b) Four decided items in that category (3 donate, 1 sell) -> a new item in
      the same category is suggested `donate`, reason "donated 3 of 4 …".
  (c) An unidentified item is left alone even when a pattern exists — a real
      pattern must not be applied to a guess.

Idempotent: fixed ids, and this estate's override logs for the category under
test are cleared before the run.

Usage:
    .venv/bin/python test_overrides.py

Exit codes: 0 both cases behaved, 1 a real logic failure, 2 the Gemini API
refused the call so there was no category to build a history for.
"""

import sys
from pathlib import Path

from claims import record_claim
from classify import Classification, classify_image
from dispositions import (
    DispositionError,
    get_disposition_decision,
    record_disposition_decision,
)
from firebase_app import PROJECT_ID, get_db
from items import create_item_from_classification, suggestion_for
from membership import MembershipError, accept_invite, create_auth_user, invite_to_estate
from models import (
    Item,
    ItemStatus,
    MembershipRole,
    OverrideLog,
    ResolutionType,
    SuggestedDisposition,
)
from overrides import NO_PATTERN_SIGNAL, get_override_history, suggest_disposition
from resolutions import resolve_item
from test_claims import BENEFICIARIES, ESTATE_ID, reset_item
from test_resolutions import EXECUTOR, clear_resolution

SAMPLE_IMAGE = Path(__file__).parent / "test_data" / "sample_item.png"

# Four items that build the estate's habit, and two that test against it.
HISTORY_ITEM_IDS = [f"test-override-hist-{n}" for n in range(1, 5)]
HISTORY_DECISIONS = [
    SuggestedDisposition.DONATE,
    SuggestedDisposition.DONATE,
    SuggestedDisposition.SELL,
    SuggestedDisposition.DONATE,
]
NEW_ITEM_NO_HISTORY = "test-override-new-cold"
NEW_ITEM_WITH_PATTERN = "test-override-new-warm"
NEW_ITEM_UNIDENTIFIED = "test-override-new-unknown"


def clear_category_history(category: str) -> int:
    """Drop this estate's logged decisions for `category` so the run starts cold."""
    db = get_db()
    entries = get_override_history(ESTATE_ID, category)
    for entry in entries:
        db.collection(OverrideLog.COLLECTION).document(entry.id).delete()
    return len(entries)


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


def check_in(failures: list[str], label: str, needle: str, haystack: str) -> None:
    if needle.lower() in haystack.lower():
        print(f"  ok       {label}")
    else:
        failures.append(f"{label}: {needle!r} not in {haystack!r}")
        print(f"  FAIL     {label}: {needle!r} missing")


def build_decided_item(
    item_id: str,
    category: str,
    claimant_uid: str,
    executor_uid: str,
    choice: SuggestedDisposition,
) -> None:
    """Take one item all the way to a logged disposition decision.

    Deliberately the long way round — claim, resolve, decide — rather than
    writing an OverrideLog row directly, so the history under test is history
    the real flow could actually have produced.
    """
    reset_item(item_id, category, "Seeded so the estate has a habit to learn from.")
    clear_resolution(item_id)
    record_claim(item_id, claimant_uid)
    resolve_item(
        item_id,
        resolved_by_user_id=executor_uid,
        resolution_type=ResolutionType.ASSIGNED_TO_CLAIMANT,
        resolved_to_user_id=claimant_uid,
        notes="Seeded for the override-history test.",
    )
    record_disposition_decision(item_id, choice, executor_uid)


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

    # One real classification, reused throughout — the category has to be a
    # category Gemini actually returns, not one invented for the test.
    classification = classify_image(str(SAMPLE_IMAGE))
    if classification.error:
        print(f"\nBLOCKED — the Gemini API refused the call: {classification.error}")
        print("There is no real category to build a history for, so the adaptive")
        print("loop could not be exercised. This is billing/quota, not logic.")
        return 2

    category = classification.ai_category
    print(f"  classified   {SAMPLE_IMAGE.name} -> {category!r} "
          f"(confidence {classification.ai_classification_confidence})")

    cleared = clear_category_history(category)
    if cleared:
        print(f"  cleaned      {cleared} override log(s) in {category!r}")
    check(failures, "history starts empty", len(get_override_history(ESTATE_ID, category)), 0)
    print()

    # --- (a) cold start: no pattern, no guess ------------------------------
    print(f"(a) new {category!r} item with no history for the category")
    cold = suggest_disposition(ESTATE_ID, category)
    print(f"           reason: {cold.reason}")
    check(failures, "suggestion", cold.suggested_disposition, SuggestedDisposition.UNCERTAIN)
    check(failures, "has_pattern", cold.has_pattern, False)
    check(failures, "history_count", cold.history_count, 0)
    check_in(failures, f"says {NO_PATTERN_SIGNAL!r}", NO_PATTERN_SIGNAL, cold.reason)

    cold_item = create_item_from_classification(
        ESTATE_ID, classification, item_id=NEW_ITEM_NO_HISTORY
    )
    check(
        failures, "stored suggested_disposition",
        read_item(NEW_ITEM_NO_HISTORY).suggested_disposition,
        SuggestedDisposition.UNCERTAIN,
    )
    # Confidence is the classifier's, and the override log never touches it.
    check(
        failures, "confidence passed through unchanged",
        cold_item.ai_classification_confidence,
        classification.ai_classification_confidence,
    )
    print()

    # --- build the estate's habit ------------------------------------------
    print(f"building history: 4 resolved {category!r} items")
    for item_id, choice in zip(HISTORY_ITEM_IDS, HISTORY_DECISIONS):
        build_decided_item(item_id, category, beneficiary_uid, executor_uid, choice)
        print(f"  decided  {item_id}  -> {choice.value}")

    history = get_override_history(ESTATE_ID, category)
    check(failures, "history entries", len(history), 4)
    # Agreements are logged too, not only corrections — the tally counts totals.
    logged = get_disposition_decision(HISTORY_ITEM_IDS[0])
    if logged is None:
        failures.append("no override log written for the first decided item")
        print("  FAIL     no override log written for the first decided item")
    else:
        check(failures, "item_category denormalized", logged.item_category, category)
        check(
            failures, "ai_suggested_disposition recorded",
            logged.ai_suggested_disposition, SuggestedDisposition.UNCERTAIN,
        )
        check(
            failures, "executor_chosen_disposition recorded",
            logged.executor_chosen_disposition, SuggestedDisposition.DONATE,
        )
    print()

    # --- (b) the same classification, now adapted --------------------------
    print(f"(b) new {category!r} item after 3 donate / 1 sell")
    warm = suggestion_for(ESTATE_ID, classification)
    print(f"           reason: {warm.reason}")
    check(failures, "suggestion", warm.suggested_disposition, SuggestedDisposition.DONATE)
    check(failures, "has_pattern", warm.has_pattern, True)
    check(failures, "matching_count", warm.matching_count, 3)
    check(failures, "history_count", warm.history_count, 4)
    check_in(failures, "reason gives the tally", "3 of 4", warm.reason)

    create_item_from_classification(
        ESTATE_ID, classification, item_id=NEW_ITEM_WITH_PATTERN
    )
    check(
        failures, "stored suggested_disposition",
        read_item(NEW_ITEM_WITH_PATTERN).suggested_disposition,
        SuggestedDisposition.DONATE,
    )
    print()

    # --- (c) a pattern must not be applied to a guess ----------------------
    print("(c) an unidentified item, with the same pattern in place")
    unidentified = Classification(
        ai_category=category,
        ai_condition_notes="Couldn't make it out.",
        ai_classification_confidence=0.0,
    )
    check(failures, "routes to", unidentified.status, ItemStatus.NEEDS_CLARIFICATION)
    guessy = suggestion_for(ESTATE_ID, unidentified)
    print(f"           reason: {guessy.reason}")
    check(failures, "suggestion", guessy.suggested_disposition, SuggestedDisposition.UNCERTAIN)
    check(failures, "has_pattern", guessy.has_pattern, False)

    create_item_from_classification(
        ESTATE_ID, unidentified, item_id=NEW_ITEM_UNIDENTIFIED
    )
    stored = read_item(NEW_ITEM_UNIDENTIFIED)
    check(failures, "stored suggested_disposition", stored.suggested_disposition,
          SuggestedDisposition.UNCERTAIN)
    check(failures, "stored status", stored.status, ItemStatus.NEEDS_CLARIFICATION)
    print()

    # --- the placeholder's own gates ---------------------------------------
    print("record_disposition_decision gates")
    try:
        record_disposition_decision(
            HISTORY_ITEM_IDS[0], SuggestedDisposition.SELL, beneficiary_uid
        )
        failures.append("a beneficiary was allowed to decide a disposition")
        print("  FAIL     beneficiary was allowed to decide a disposition")
    except MembershipError as exc:
        print(f"  ok       non-executor refused: {exc}")

    try:
        # NEW_ITEM_WITH_PATTERN was never claimed or resolved.
        record_disposition_decision(
            NEW_ITEM_WITH_PATTERN, SuggestedDisposition.DONATE, executor_uid
        )
        failures.append("an unresolved item accepted a disposition decision")
        print("  FAIL     unresolved item accepted a disposition decision")
    except DispositionError as exc:
        print(f"  ok       unresolved item refused: {exc}")

    check(failures, "no stray log written", get_disposition_decision(NEW_ITEM_WITH_PATTERN), None)
    check(failures, "history still 4", len(get_override_history(ESTATE_ID, category)), 4)
    print()

    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("OK — cold start says so plainly, and the same photo adapts to donate "
          "once the estate has a habit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
