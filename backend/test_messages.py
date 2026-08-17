"""End-to-end check of the two agent Message behaviors against real Firestore.

Not a test suite — a script. Three cases, all against the live project:

  (a) The blank square from test_classify.py routes to `needs_clarification`
      and produces exactly one clarifying Message, authored by the agent user.
  (b) The two-claimant item from test_claims.py flips to `contested` and
      produces exactly one mediation Message, posted on the transition.
  (c) Recomputing the already-contested item posts nothing further — the same
      single message, with its original created_at untouched.

Idempotent: fixed ids, and any messages or claims left by a previous run are
deleted before the run starts, so each case is genuinely exercised rather than
reading back yesterday's document.

Usage:
    .venv/bin/python test_messages.py
"""

import sys
from pathlib import Path

from google.cloud.firestore_v1.base_query import FieldFilter

from claims import recompute_item_status, record_claim
from firebase_app import PROJECT_ID, get_db
from items import classify_and_create_item
from membership import accept_invite, create_auth_user, invite_to_estate
from messages import agent_message_id, get_agent_user, get_messages_for_item
from models import ItemStatus, MembershipRole, Message, RoleType
from test_claims import BENEFICIARIES, ESTATE_ID, ITEM_B_ID, reset_item
from test_classify import BLANK_IMAGE, BLANK_ITEM_ID, make_blank_square



from test_guard import require_destructive_ok

require_destructive_ok(__name__, "test_messages.py", "the test-message items and their threads")

def clear_messages(item_id: str) -> int:
    """Delete every message about `item_id` so this run posts its own."""
    stale = (
        get_db()
        .collection(Message.COLLECTION)
        .where(filter=FieldFilter("item_id", "==", item_id))
        .get()
    )
    for snapshot in stale:
        snapshot.reference.delete()
    return len(stale)


def check(failures: list[str], label: str, actual, expected) -> None:
    def show(value):
        return value.value if hasattr(value, "value") else value

    if actual == expected:
        print(f"  ok       {label}: {show(actual)}")
    else:
        failures.append(f"{label}: got {show(actual)}, expected {show(expected)}")
        print(f"  FAIL     {label}: got {show(actual)}, expected {show(expected)}")


def show_message(message: Message) -> None:
    print(f"           id        {message.id}")
    print(f"           author    {message.user_id}")
    print(f"           item_id   {message.item_id}")
    for line in message.text.splitlines():
        print(f"           | {line}" if line else "           |")


def main() -> int:
    print(f"Project: {PROJECT_ID}")
    print(f"Estate:  {ESTATE_ID}\n")

    failures: list[str] = []

    # --- The agent's own User row ------------------------------------------
    print("agent user")
    agent = get_agent_user()
    print(f"  id           {agent.id}")
    print(f"  display_name {agent.display_name}")
    check(failures, "role_type", agent.role_type, RoleType.AGENT)
    # Reused, not recreated, on a second call.
    check(failures, "stable across calls", get_agent_user().id, agent.id)
    print()

    # --- (a) Clarifying question on a needs_clarification item -------------
    print("(a) blank square -> needs_clarification -> clarifying message")
    cleared = clear_messages(BLANK_ITEM_ID)
    if cleared:
        print(f"  cleaned  {cleared} message(s) from a previous run")

    make_blank_square(Path(BLANK_IMAGE))
    blank_item, blank_classification = classify_and_create_item(
        ESTATE_ID,
        str(BLANK_IMAGE),
        photo_urls=[f"file://{BLANK_IMAGE}"],
        item_id=BLANK_ITEM_ID,
    )
    if blank_classification.error:
        print(f"  note     classifier error — {blank_classification.error}")
        print("           (the failure path routes here too, so the case still holds)")
    check(failures, "item status", blank_item.status, ItemStatus.NEEDS_CLARIFICATION)

    clarify = get_messages_for_item(BLANK_ITEM_ID)
    check(failures, "messages on the item", len(clarify), 1)
    if clarify:
        message = clarify[0]
        show_message(message)
        check(failures, "authored by the agent", message.user_id, agent.id)
        check(failures, "item_id set", message.item_id, BLANK_ITEM_ID)
        check(failures, "estate_id set", message.estate_id, ESTATE_ID)
        check(
            failures,
            "deterministic id",
            message.id,
            agent_message_id("clarify", BLANK_ITEM_ID),
        )
        # Tone guard: the family should never see the internal vocabulary.
        jargon = [
            word
            for word in ("confidence", "threshold", "classification", "error", "null")
            if word in message.text.lower()
        ]
        check(failures, "no internal jargon in the copy", jargon, [])
    print()

    # --- (b) Mediation posted on the transition into contested -------------
    print("(b) two claimants -> contested -> mediation message")
    uids = []
    for email, display_name in BENEFICIARIES:
        uid = create_auth_user(email, display_name)
        invite_to_estate(ESTATE_ID, email, MembershipRole.BENEFICIARY)
        accept_invite(ESTATE_ID, uid)
        uids.append(uid)
    uid_one, uid_two = uids

    reset_item(ITEM_B_ID, "furniture", "Walnut side table, ring mark on top.")
    cleared = clear_messages(ITEM_B_ID)
    if cleared:
        print(f"  cleaned  {cleared} message(s) from a previous run")

    _, status_first = record_claim(ITEM_B_ID, uid_one)
    check(failures, "status after 1st claim", status_first, ItemStatus.CLAIMED)
    # One claimant is not a conflict — the agent has nothing to mediate yet.
    check(failures, "messages after 1st claim", len(get_messages_for_item(ITEM_B_ID)), 0)

    _, status_second = record_claim(
        ITEM_B_ID, uid_two, comment="This was in my room growing up."
    )
    check(failures, "status after 2nd claim", status_second, ItemStatus.CONTESTED)

    mediation = get_messages_for_item(ITEM_B_ID)
    check(failures, "messages on the item", len(mediation), 1)
    if not mediation:
        print("\ncannot check (c) without the mediation message from (b).")
        print(f"\n{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    message = mediation[0]
    show_message(message)
    check(failures, "authored by the agent", message.user_id, agent.id)
    check(failures, "item_id set", message.item_id, ITEM_B_ID)
    check(
        failures,
        "deterministic id",
        message.id,
        agent_message_id("mediate", ITEM_B_ID),
    )
    # It should name both people and offer all three paths from the data model.
    names = [display for _, display in BENEFICIARIES]
    check(
        failures,
        "names both claimants",
        all(name in message.text for name in names),
        True,
    )
    # It has to propose a way through, not just acknowledge the conflict. One
    # named path is the bar; the copy currently weaves in all three.
    paths = {
        "assign": "take it",
        "share": "sharing it",
        "appraise": "appraised",
    }
    named = [name for name, phrase in paths.items() if phrase in message.text.lower()]
    check(failures, "names a resolution path", bool(named), True)
    print(f"           paths named: {', '.join(named) if named else 'none'}")
    # Prose, not a menu — a list of choices reads like a form to fill in.
    check(failures, "not a bulleted menu", "•" in message.text, False)
    print()

    # --- (c) Recompute while already contested says nothing new ------------
    print("(c) recompute on the already-contested item -> no second message")
    original_created_at = message.created_at

    status_again = recompute_item_status(ITEM_B_ID)
    check(failures, "status unchanged", status_again, ItemStatus.CONTESTED)

    after = get_messages_for_item(ITEM_B_ID)
    check(failures, "still exactly one message", len(after), 1)
    if after:
        check(failures, "same message id", after[0].id, message.id)
        # An overwrite would stamp a new created_at even though the count held.
        check(failures, "created_at untouched", after[0].created_at, original_created_at)

    # A third claim from a user who already claimed keeps it contested and still
    # silent — the transition happened once, so the agent spoke once.
    record_claim(ITEM_B_ID, uid_two, comment="Still hoping for it.")
    recompute_item_status(ITEM_B_ID)
    check(failures, "silent after a repeat claim", len(get_messages_for_item(ITEM_B_ID)), 1)
    print()

    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("OK — clarifying question, mediation on transition, and no double-post.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
