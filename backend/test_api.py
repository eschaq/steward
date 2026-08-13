"""End-to-end check of the ADK + FastAPI path against real Firestore.

Not a test suite — a script. It drives the API with FastAPI's TestClient (no
live server, no port) and checks that a Message posted through the new
ADK-wrapped path is byte-identical to what the direct path in messages.py would
have written, and that it still refuses to post twice.

  (a) needs_clarification -> POST writes the clarifying question; the text equals
      messages.clarifying_question_text() for the same item. A second POST
      reports it was already asked and leaves the message alone.
  (b) contested -> POST writes the mediating suggestion; the text equals
      messages.mediation_text() for the same claimants, named in the same order.
      A second POST leaves it alone.
  (c) An item in a state no behavior attaches to is a 409, and an unknown item
      is a 404 — not a 200 that quietly did nothing.

Idempotent: fixed ids, and any messages left by a previous run are cleared first.

Usage:
    .venv/bin/python test_api.py
"""

import sys
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api import app
from claims import claimant_ids_for_item, record_claim
from dev_tokens import bearer
from firebase_app import PROJECT_ID, get_db
from init_firestore import to_firestore
from membership import accept_invite, create_auth_user, invite_to_estate
from messages import clarifying_question_text, get_messages_for_item, mediation_text
from models import Item, ItemStatus, MembershipRole, SuggestedDisposition, User
from test_claims import BENEFICIARIES, ESTATE_ID, reset_item
from test_messages import clear_messages

CLARIFY_ITEM = "test-api-clarify"
CONTESTED_ITEM = "test-api-contested"
INELIGIBLE_ITEM = "test-api-unclaimed"
MISSING_ITEM = "test-api-no-such-item"

CLARIFY_CATEGORY = "unknown"
CLARIFY_NOTES = "A solid grey-blue field; nothing identifiable in frame."

client = TestClient(app)

# The agent route sits behind auth now: a verified accepted member of the estate.
AUTH: dict[str, str] = {}


def write_item(item_id: str, category: str, notes: str, status: ItemStatus) -> Item:
    """Put an item straight into a given state, without going through Gemini."""
    item = Item(
        id=item_id,
        estate_id=ESTATE_ID,
        photo_urls=[],
        ai_category=category,
        ai_condition_notes=notes,
        ai_est_era_or_brand=None,
        ai_classification_confidence=0.0 if status is ItemStatus.NEEDS_CLARIFICATION else 0.9,
        suggested_disposition=SuggestedDisposition.UNCERTAIN,
        status=status,
        created_at=datetime.now(timezone.utc),
    )
    get_db().collection(Item.COLLECTION).document(item_id).set(to_firestore(item))
    return item


def display_name(user_id: str) -> str:
    """Read a claimant's name the way the family would see it."""
    snapshot = get_db().collection(User.COLLECTION).document(user_id).get()
    return (snapshot.to_dict() or {}).get("display_name") or "someone"


def check(failures: list[str], label: str, actual, expected) -> None:
    def show(value):
        return value.value if hasattr(value, "value") else value

    if actual == expected:
        print(f"  ok       {label}: {show(actual)}")
    else:
        failures.append(f"{label}: got {show(actual)!r}, expected {show(expected)!r}")
        print(f"  FAIL     {label}: got {show(actual)!r}, expected {show(expected)!r}")


def check_posts_once(
    failures: list[str], item_id: str, expected_text: str, repeat_status: str
) -> None:
    """POST once, then again: same message, written once, content unchanged."""
    first = client.post(f"/items/{item_id}/agent-message", headers=AUTH)
    check(failures, "first POST", first.status_code, 200)
    if first.status_code != 200:
        print(f"           body: {first.text}")
        return

    body = first.json()
    check(failures, "status", body["status"], "posted")

    posted = get_messages_for_item(item_id)
    check(failures, "messages on the item", len(posted), 1)
    if not posted:
        return

    message = posted[0]
    check(failures, "message_id echoed", body["message_id"], message.id)
    # The whole point: the ADK path wrote what the direct path would have.
    check(failures, "text identical to messages.py", message.text, expected_text)

    created_at = message.created_at
    second = client.post(f"/items/{item_id}/agent-message", headers=AUTH)
    check(failures, "second POST", second.status_code, 200)
    check(failures, "second status", second.json()["status"], repeat_status)
    after = get_messages_for_item(item_id)
    check(failures, "still exactly one message", len(after), 1)
    if after:
        check(failures, "created_at untouched", after[0].created_at, created_at)


def main() -> int:
    print(f"Project: {PROJECT_ID}")
    print(f"Estate:  {ESTATE_ID}\n")

    failures: list[str] = []

    print("setup")
    health = client.get("/healthz")
    check(failures, "healthz", health.status_code, 200)

    AUTH.update(bearer(BENEFICIARIES[0][0], BENEFICIARIES[0][1]))

    uids = []
    for email, name in BENEFICIARIES:
        uid = create_auth_user(email, name)
        invite_to_estate(ESTATE_ID, email, MembershipRole.BENEFICIARY)
        accept_invite(ESTATE_ID, uid)
        uids.append(uid)
    uid_one, uid_two = uids

    write_item(CLARIFY_ITEM, CLARIFY_CATEGORY, CLARIFY_NOTES, ItemStatus.NEEDS_CLARIFICATION)
    clear_messages(CLARIFY_ITEM)

    # Built through the real claim flow, which posts mediation on the transition;
    # clearing it afterwards leaves the endpoint to do the posting.
    reset_item(CONTESTED_ITEM, "furniture", "Walnut side table, ring mark on top.")
    record_claim(CONTESTED_ITEM, uid_one)
    record_claim(CONTESTED_ITEM, uid_two, comment="This was in my room growing up.")
    clear_messages(CONTESTED_ITEM)

    write_item(INELIGIBLE_ITEM, "linens", "Boxed tablecloths.", ItemStatus.UNCLAIMED)
    print(f"  items        {CLARIFY_ITEM}, {CONTESTED_ITEM}, {INELIGIBLE_ITEM}\n")

    # --- (a) the clarifying question ---------------------------------------
    print(f"(a) POST /items/{CLARIFY_ITEM}/agent-message  (needs_clarification)")
    expected = clarifying_question_text(CLARIFY_CATEGORY, CLARIFY_NOTES)
    first = client.post(f"/items/{CLARIFY_ITEM}/agent-message", headers=AUTH)
    if first.status_code == 200:
        check(failures, "behavior", first.json()["behavior"], "ask_about_unclear_item")
        check(failures, "item_status", first.json()["item_status"], "needs_clarification")
    # Re-run the pair from a clean slate so the assertions above and below agree.
    clear_messages(CLARIFY_ITEM)
    check_posts_once(failures, CLARIFY_ITEM, expected, "already_asked")
    print(f"           | {get_messages_for_item(CLARIFY_ITEM)[0].text[:78]}…")
    print()

    # --- (b) the mediating suggestion --------------------------------------
    print(f"(b) POST /items/{CONTESTED_ITEM}/agent-message  (contested)")
    names = [display_name(uid) for uid in claimant_ids_for_item(CONTESTED_ITEM)]
    print(f"           claimants: {', '.join(names)}")
    first = client.post(f"/items/{CONTESTED_ITEM}/agent-message", headers=AUTH)
    if first.status_code == 200:
        check(failures, "behavior", first.json()["behavior"], "mediate_contested_item")
        check(failures, "item_status", first.json()["item_status"], "contested")
    clear_messages(CONTESTED_ITEM)
    check_posts_once(failures, CONTESTED_ITEM, mediation_text(names), "already_mediated")
    print(f"           | {get_messages_for_item(CONTESTED_ITEM)[0].text[:78]}…")
    print()

    # --- (c) states with nothing to say ------------------------------------
    print("(c) items the agent has nothing to say about")
    ineligible = client.post(f"/items/{INELIGIBLE_ITEM}/agent-message", headers=AUTH)
    check(failures, "unclaimed item", ineligible.status_code, 409)
    print(f"           {ineligible.json().get('detail')}")
    check(failures, "no message written", len(get_messages_for_item(INELIGIBLE_ITEM)), 0)

    missing = client.post(f"/items/{MISSING_ITEM}/agent-message", headers=AUTH)
    check(failures, "unknown item", missing.status_code, 404)
    print(f"           {missing.json().get('detail')}")
    print()

    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("OK — both behaviors run through ADK over HTTP, byte-identical copy, "
          "still no double-post.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
