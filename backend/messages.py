"""The Message Center: the estate's single unified feed, and the agent's voice in it.

Per docs/estate-agent-data-model.md, agent-authored guidance goes through the
same `messages` collection humans use — there is no separate notification
system. The author is a User row with `role_type=agent`.

Two agent behaviors post here, both required by the Collaborative Partner brief:

  * clarifying questions — when an item lands in `needs_clarification`
  * contested-item mediation — the moment an item flips to `contested`

Copy in this module is read by a grieving family. Tone follows
docs/estate-agent-branding.md: warm, unhurried, plainspoken — a quiet, steady
hand at a kitchen table. No urgency, no nudging, no reseller register.
"""

import sys
from enum import Enum
from typing import Optional

from google.cloud.firestore_v1.base_query import FieldFilter

from firebase_app import get_db
from models import Message, RoleType, User

# The agent's own User row. It is a Firestore document only — the agent never
# signs in, so it deliberately has no Firebase Auth account.
AGENT_USER_ID = "steward-agent"
AGENT_EMAIL = "agent@steward.local"
AGENT_DISPLAY_NAME = "Steward"


def _to_firestore(model) -> dict:
    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in model.model_dump().items()
    }


def get_agent_user() -> User:
    """The User that authors agent messages — reused if one already exists.

    Looks for the well-known document id first, then for any other user with
    `role_type=agent` (so an agent row created elsewhere is adopted rather than
    duplicated), and only creates one if neither turns up.
    """
    db = get_db()

    snapshot = db.collection(User.COLLECTION).document(AGENT_USER_ID).get()
    if snapshot.exists:
        return User.model_validate(snapshot.to_dict())

    existing = (
        db.collection(User.COLLECTION)
        .where(filter=FieldFilter("role_type", "==", RoleType.AGENT.value))
        .limit(1)
        .get()
    )
    if existing:
        return User.model_validate(existing[0].to_dict())

    agent = User(
        id=AGENT_USER_ID,
        email=AGENT_EMAIL,
        display_name=AGENT_DISPLAY_NAME,
        role_type=RoleType.AGENT,
    )
    db.collection(User.COLLECTION).document(agent.id).set(_to_firestore(agent))
    return agent


def post_message(
    estate_id: str,
    user_id: str,
    text: str,
    item_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> Message:
    """Write one message to the feed.

    `item_id` stays None for general estate discussion. Passing `message_id`
    pins the document id, which is how the agent's once-per-item posts stay
    once-per-item.
    """
    db = get_db()
    doc_ref = (
        db.collection(Message.COLLECTION).document(message_id)
        if message_id
        else db.collection(Message.COLLECTION).document()
    )
    message = Message(
        id=doc_ref.id,
        estate_id=estate_id,
        item_id=item_id,
        user_id=user_id,
        text=text,
    )
    doc_ref.set(_to_firestore(message))
    return message


def get_messages_for_item(item_id: str) -> list[Message]:
    """Every message about `item_id`, oldest first.

    Single-field equality filter, so Firestore's automatic index covers it.
    """
    snapshots = (
        get_db()
        .collection(Message.COLLECTION)
        .where(filter=FieldFilter("item_id", "==", item_id))
        .get()
    )
    messages = [Message.model_validate(s.to_dict()) for s in snapshots]
    return sorted(messages, key=lambda m: m.created_at)


def get_messages_for_estate(estate_id: str) -> list[Message]:
    """The whole feed for an estate — item-specific and general together."""
    snapshots = (
        get_db()
        .collection(Message.COLLECTION)
        .where(filter=FieldFilter("estate_id", "==", estate_id))
        .get()
    )
    messages = [Message.model_validate(s.to_dict()) for s in snapshots]
    return sorted(messages, key=lambda m: m.created_at)


# --- Agent behaviors -------------------------------------------------------
#
# Both use a deterministic message id, so the agent says a given thing about a
# given item exactly once no matter how often the surrounding code runs.

def agent_message_id(behavior: str, item_id: str) -> str:
    return f"agent-{behavior}__{item_id}"


def _post_once(
    behavior: str, estate_id: str, item_id: str, text: str
) -> Optional[Message]:
    """Post an agent message about an item, unless that message is already there.

    Returns the new Message, or None if the agent had already said this.

    A failure to post never propagates: the item upload or the claim that
    triggered it has already happened, and losing that work over a feed write
    would be worse than a missing message. The failure is printed rather than
    swallowed.
    """
    message_id = agent_message_id(behavior, item_id)
    try:
        db = get_db()
        if db.collection(Message.COLLECTION).document(message_id).get().exists:
            return None
        return post_message(
            estate_id=estate_id,
            user_id=get_agent_user().id,
            text=text,
            item_id=item_id,
            message_id=message_id,
        )
    except Exception as exc:  # noqa: BLE001 — the trigger has already committed
        print(
            f"warning: could not post the {behavior} message for item {item_id} "
            f"({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )
        return None


def clarifying_question_text(
    ai_category: Optional[str] = None, ai_condition_notes: Optional[str] = None
) -> str:
    """What the agent says when it couldn't place an item from the photo.

    If it has a half-formed guess, it offers it and says plainly that it isn't
    sure — more useful to the family than a blank shrug, and honest either way.
    """
    guess = (ai_category or "").strip().lower()
    if guess and guess != "unknown":
        # "My best guess is X" rather than "It might be a X": categories are a
        # mix of singular ("armchair"), plural ("photographs") and mass nouns
        # ("artwork"), and no choice of article is right for all three.
        opening = (
            f"I couldn't quite place this one. My best guess is {guess}, "
            "but I'd rather ask than guess."
        )
    else:
        opening = "I couldn't quite place this one from the photo."

    return (
        f"{opening} Can you tell me more about it — what it is, roughly how old, "
        "anything you remember? A clearer photo would help too, if there's one "
        "handy. No rush; it'll sit here until someone gets to it."
    )


def post_clarifying_question(
    estate_id: str,
    item_id: str,
    ai_category: Optional[str] = None,
    ai_condition_notes: Optional[str] = None,
) -> Optional[Message]:
    """Ask the family to help identify an item that landed in needs_clarification."""
    return _post_once(
        "clarify",
        estate_id,
        item_id,
        clarifying_question_text(ai_category, ai_condition_notes),
    )


def display_names_for(user_ids: list[str]) -> dict[str, str]:
    """Display names for a set of authors, in one pass.

    The frontend can't read `users` — firestore.rules allows a caller their own
    document and nothing else — so a feed rendered client-side would show bare
    uids without this. Resolved here rather than by opening up that rule.
    """
    db = get_db()
    names: dict[str, str] = {}
    for user_id in dict.fromkeys(user_ids):
        snapshot = db.collection(User.COLLECTION).document(user_id).get()
        data = snapshot.to_dict() if snapshot.exists else None
        names[user_id] = (data or {}).get("display_name") or "someone"
    return names


def _claimant_names(user_ids: list[str]) -> list[str]:
    """Display names for the people who claimed an item, in the order given."""
    db = get_db()
    names = []
    for user_id in user_ids:
        snapshot = db.collection(User.COLLECTION).document(user_id).get()
        data = snapshot.to_dict() if snapshot.exists else None
        names.append((data or {}).get("display_name") or "someone")
    return names


def mediation_text(claimant_names: Optional[list[str]] = None) -> str:
    """What the agent says the moment an item becomes contested.

    Names the situation without taking a side, then proposes a way through —
    acknowledgement alone leaves the family exactly where they started. All
    three of the Resolution paths are here (assign to one claimant, share or
    rotate, outside appraisal), written as prose rather than a bulleted menu:
    a list of choices reads like a form to fill in, which is the wrong register
    for the moment this message lands in.

    Deliberately unhurried — nothing here should read as pressure to settle it
    today.
    """
    names = [n for n in (claimant_names or []) if n]
    if len(names) == 2:
        who = f"{names[0]} and {names[1]} have both"
    elif len(names) > 2:
        who = f"{', '.join(names[:-1])} and {names[-1]} have all"
    else:
        who = "More than one person has"

    return (
        f"{who} asked for this one. That usually means it mattered to more than "
        "one person, and it's worth talking through rather than settling "
        "quickly.\n\n"
        "Often the simplest way through is for one of you to take it, and the "
        "other to get first choice on something of similar meaning. If neither "
        "of you wants to be the one who lets go, sharing it works too — a while "
        "in one house, then the other. And if what's really in the way is that "
        "nobody knows what it's worth, having it appraised first can take that "
        "question off the table.\n\n"
        "Whenever you've talked it over, the executor can record what you "
        "decided here. No hurry — it'll stay marked contested until then."
    )


def post_contested_mediation(
    estate_id: str, item_id: str, claimant_user_ids: Optional[list[str]] = None
) -> Optional[Message]:
    """Post the mediating suggestion for an item that has just become contested.

    Called on the transition into `contested`, not on every recompute — see
    claims.recompute_item_status.
    """
    names = _claimant_names(claimant_user_ids) if claimant_user_ids else []
    return _post_once("mediate", estate_id, item_id, mediation_text(names))
