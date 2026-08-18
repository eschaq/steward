"""Does removing an empty estate work, and does it refuse everything else?

Not a test suite — a script, against the real project like every other one here.

It builds its **own** throwaway estates rather than touching a fixture, which
matters more for this one than for any other suite in the directory: the thing
under test deletes estates. A shared fixture and an off-by-one in the emptiness
check is how you lose the seeded demo estate the afternoon before a demo.

Usage:
    STEWARD_ALLOW_DESTRUCTIVE_TESTS=1 .venv/bin/python test_estate_delete.py
"""

import sys

from google.cloud import firestore as gcf

from firebase_app import PROJECT_ID, get_db
from membership import (
    MembershipError,
    create_auth_user,
    create_estate,
    delete_empty_estate,
    invite_to_estate,
    membership_id,
)
from models import (
    Estate,
    EstateMembership,
    Item,
    ItemStatus,
    MembershipRole,
    Message,
    SuggestedDisposition,
)

from test_guard import require_destructive_ok

require_destructive_ok(
    __name__,
    "test_estate_delete.py",
    "throwaway estates it creates itself (no shared fixtures)",
)

OWNER = "steward-test-executor@example.com"
OTHER = "steward-test-beneficiary@example.com"

passed: list[str] = []
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (passed if ok else failed).append(name)
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{f' — {detail}' if detail else ''}")


def refuses(estate_id: str, uid: str) -> str:
    """Delete and expect a refusal; returns the message."""
    try:
        delete_empty_estate(estate_id, uid)
    except MembershipError as exc:
        return str(exc)
    return ""


PREFIX = "Delete Me — "


def sweep_leftovers(owner: str) -> None:
    """Clear any throwaway estate a previous run left behind.

    Every estate this script makes is named with `PREFIX`, and every one is
    meant to be gone by the end. A run that fails partway — which is what a
    failing test *is* — leaves one in the switcher of whoever owns the test
    account, and a list of debris is how a real estate eventually gets deleted
    by someone clearing up. So each run tidies the last one's mess first.
    """
    from membership import estates_for_user

    for estate, _role in estates_for_user(owner):
        if not estate.name.startswith(PREFIX):
            continue
        try:
            delete_empty_estate(estate.id, owner)
            print(f"  swept a leftover: {estate.name}")
        except MembershipError as exc:
            # Left deliberately: it has something in it, so the same rule that
            # protects a real estate protects this one from a blind cleanup.
            print(f"  left alone ({estate.name}): {exc}")


def main() -> int:
    print(f"project: {PROJECT_ID}\n")
    db = get_db()
    owner = create_auth_user(OWNER, "Test Executor")
    other = create_auth_user(OTHER, "Test Beneficiary")
    sweep_leftovers(owner)

    # --- 1. the ordinary case: made by mistake, never used ------------------
    empty = create_estate(f"{PREFIX}empty", owner)
    removed = delete_empty_estate(empty.id, owner)
    check("an empty estate is removed", removed.id == empty.id)
    check(
        "the estate document is gone",
        not db.collection(Estate.COLLECTION).document(empty.id).get().exists,
    )
    check(
        "the executor's membership goes with it",
        not db.collection(EstateMembership.COLLECTION)
        .document(membership_id(empty.id, owner))
        .get()
        .exists,
        "otherwise it lists an estate that no longer exists",
    )
    check("removing it twice is refused, not silent", bool(refuses(empty.id, owner)))

    # --- 2. an estate with a belonging in it -------------------------------
    with_item = create_estate(f"{PREFIX}has an item", owner)
    item = Item(
        id=f"test-delete-item-{with_item.id}",
        estate_id=with_item.id,
        ai_category="chair",
        ai_condition_notes="a test fixture, not a chair",
        ai_classification_confidence=0.9,
        suggested_disposition=SuggestedDisposition.UNCERTAIN,
        status=ItemStatus.UNCLAIMED,
    )
    db.collection(Item.COLLECTION).document(item.id).set(item.model_dump(mode="json"))
    message = refuses(with_item.id, owner)
    check("an estate with a belonging is refused", "belongings in it" in message, message)

    # A soft-removed item is still a record with things hanging off it, and is
    # exactly the case an emptiness check written against the dashboard's own
    # filters would miss.
    db.collection(Item.COLLECTION).document(item.id).update(
        {"status": ItemStatus.REMOVED.value}
    )
    message = refuses(with_item.id, owner)
    check("a soft-removed belonging still blocks it", "belongings in it" in message, message)
    db.collection(Item.COLLECTION).document(item.id).delete()
    check(
        "and it can be removed once that belonging is gone",
        delete_empty_estate(with_item.id, owner).id == with_item.id,
    )

    # --- 3. an estate with only a conversation in it -----------------------
    # Message.item_id is nullable by design, so this is reachable with no items.
    with_talk = create_estate(f"{PREFIX}has a message", owner)
    note = Message(
        id=f"test-delete-msg-{with_talk.id}",
        estate_id=with_talk.id,
        user_id=owner,
        item_id=None,
        text="Somebody's words, in an estate with nothing in it.",
    )
    db.collection(Message.COLLECTION).document(note.id).set(note.model_dump(mode="json"))
    message = refuses(with_talk.id, owner)
    check("an estate holding only a message is refused", "messages in it" in message, message)
    db.collection(Message.COLLECTION).document(note.id).delete()
    delete_empty_estate(with_talk.id, owner)

    # --- 4. an estate somebody else has been asked into --------------------
    shared = create_estate(f"{PREFIX}someone invited", owner)
    invite_to_estate(shared.id, OTHER, MembershipRole.BENEFICIARY)
    message = refuses(shared.id, owner)
    check(
        "a pending invite blocks it",
        "1 other person" in message and "still invited" in message,
        message,
    )

    db.collection(EstateMembership.COLLECTION).document(
        membership_id(shared.id, other)
    ).update({"accepted_at": gcf.SERVER_TIMESTAMP})
    message = refuses(shared.id, owner)
    check("an accepted member blocks it too", "1 other person" in message, message)

    db.collection(EstateMembership.COLLECTION).document(
        membership_id(shared.id, other)
    ).delete()
    check(
        "and it can be removed once they are gone",
        delete_empty_estate(shared.id, owner).id == shared.id,
    )

    # --- 5. an estate that isn't there -------------------------------------
    check(
        "a missing estate is a refusal, not a crash",
        "No estate" in refuses("no-such-estate-at-all", owner),
    )

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    for name in failed:
        print(f"  failed: {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
