"""Auth users, estate invites, and role lookup.

Backing store is Firebase Auth (identity) plus two Firestore collections:
`users` (the User entity) and `estate_memberships` (the EstateMembership join
table). Fields follow docs/estate-agent-data-model.md exactly.

The Firebase Auth uid *is* the User.id, so a caller's uid from a verified ID
token can be used directly for role checks with no extra indirection.
"""

from typing import Optional

from firebase_admin import auth
from google.cloud import firestore as gcf

from firebase_app import get_app, get_db
from models import Estate, EstateMembership, EstateStatus, MembershipRole, RoleType, User


class MembershipError(Exception):
    """Something about an invite/accept could not be honored.

    Raised rather than guessed at — every failure here should surface as a
    visible, honest statement, never a silent no-op.
    """


def membership_id(estate_id: str, user_id: str) -> str:
    """Deterministic document id: one membership per (estate, user).

    Makes invite idempotent and lets role checks do a direct document read
    instead of a query — no composite index, no eventual-consistency window.
    """
    return f"{estate_id}__{user_id}"


def create_auth_user(email: str, display_name: Optional[str] = None) -> str:
    """Create a Firebase Auth user for `email` and mirror it into `users`.

    Idempotent: if the email is already registered, the existing uid is reused
    rather than erroring, so invite flows can be safely re-run.

    Returns the Firebase Auth uid, which is also the User document id.
    """
    get_app()
    display_name = display_name or email.split("@")[0]

    try:
        record = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        record = auth.create_user(email=email, display_name=display_name)

    user = User(
        id=record.uid,
        email=email,
        display_name=record.display_name or display_name,
        role_type=RoleType.HUMAN,
    )
    # merge=True keeps the original created_at on a re-run.
    get_db().collection(User.COLLECTION).document(user.id).set(
        {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role_type": user.role_type.value,
            "created_at": user.created_at,
        },
        merge=True,
    )
    return record.uid


def ensure_user_document(user_id: str) -> Optional[User]:
    """Mirror a Firebase Auth account into `users`, if it isn't there already.

    `create_auth_user` does this for anyone an executor invites, but a self-serve
    sign-up creates the Auth account directly in the browser and never touches
    Firestore — so without this their name and email exist nowhere the app can
    read. The frontend cannot read `users`, so every place that resolves a
    display name (the family list, message authors, claimants) would show
    "someone" forever.

    Idempotent and merge-based: an existing mirror keeps its created_at.
    """
    get_app()
    db = get_db()
    doc_ref = db.collection(User.COLLECTION).document(user_id)
    if doc_ref.get().exists:
        return None

    try:
        record = auth.get_user(user_id)
    except Exception:  # noqa: BLE001 — no Auth record is not worth failing a write
        return None

    email = record.email or ""
    user = User(
        id=user_id,
        email=email,
        # Firebase has no display name for an email/password sign-up, so the
        # local part is the best guess available. It is a name they can be
        # called by, not a claim about who they are.
        display_name=record.display_name or (email.split("@")[0] if email else "Someone"),
        role_type=RoleType.HUMAN,
    )
    doc_ref.set(
        {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role_type": user.role_type.value,
            "created_at": user.created_at,
        },
        merge=True,
    )
    return user


def create_estate(name: str, executor_user_id: str) -> Estate:
    """Start a new estate, with its creator as executor.

    **Accepted immediately, with no invite step.** Every other membership starts
    pending because somebody else asked for it; this one is the person doing the
    asking, and leaving them to accept their own invitation would be ceremony
    with nothing on the other side of it.

    The estate id is a Firestore document id rather than anything derived from
    the name — two families may both call it "Mum's house", and a slug would
    collide or leak the name into a URL.
    """
    name = (name or "").strip()
    if not name:
        raise MembershipError("An estate needs a name — even just a surname.")

    # A self-serve creator may have no `users` mirror yet — see above.
    ensure_user_document(executor_user_id)

    db = get_db()
    estate_ref = db.collection(Estate.COLLECTION).document()
    estate = Estate(
        id=estate_ref.id,
        name=name,
        executor_user_id=executor_user_id,
        status=EstateStatus.ACTIVE,
    )
    membership = EstateMembership(
        id=membership_id(estate.id, executor_user_id),
        estate_id=estate.id,
        user_id=executor_user_id,
        role=MembershipRole.EXECUTOR,
    )

    # One batch: an estate with no executor would be unreachable by anyone,
    # including the person who just made it.
    batch = db.batch()
    batch.set(estate_ref, {
        "id": estate.id,
        "name": estate.name,
        "executor_user_id": estate.executor_user_id,
        "status": estate.status.value,
        "created_at": estate.created_at,
    })
    batch.set(
        db.collection(EstateMembership.COLLECTION).document(membership.id),
        {
            "id": membership.id,
            "estate_id": membership.estate_id,
            "user_id": membership.user_id,
            "role": membership.role.value,
            "invited_at": membership.invited_at,
            "accepted_at": gcf.SERVER_TIMESTAMP,
        },
    )
    batch.commit()
    return estate


def delete_empty_estate(estate_id: str, executor_user_id: str) -> Estate:
    """Remove an estate that never had anything in it. Refuses otherwise.

    **Why deleting and not `status: closed`.** The data model has both, and they
    answer different questions. `closed` is for an estate whose work is *done* —
    it happened, it has a history, and that history is exactly what a family
    might need to look at in two years. This is for the other case: an estate
    made by mistake, or to try something out, which never held anything at all.
    Marking those closed would leave a permanent list of a person's typos in
    their own switcher.

    **Empty means empty**, and every one of these is checked rather than assumed:

      - no items, *including* soft-removed ones. `removed` items are still real
        records with claims and messages hanging off them, and the whole point
        of that status is that nothing is destroyed.
      - no messages. `Message.item_id` is nullable by design, so an estate with
        no items can still hold a conversation, and that conversation is
        somebody's words.
      - nobody else invited — not accepted, not pending. A pending invite means
        an email went out; deleting from under it would leave a live link to
        nothing.

    Anything found is reported by name in the refusal, because "cannot delete"
    without saying what is in there is the kind of message that makes a person
    delete the wrong thing next time.

    What gets removed is only ever two documents: the estate and the caller's own
    executor membership. Everything else that could reference an estate hangs off
    an Item, and there are none — so there is nothing here that can orphan a
    record. Not a cascade, and deliberately not written as one: a cascade would
    quietly grow teeth the first time somebody relaxed the emptiness check.
    """
    db = get_db()
    estate_ref = db.collection(Estate.COLLECTION).document(estate_id)
    snapshot = estate_ref.get()
    if not snapshot.exists:
        raise MembershipError(f"No estate {estate_id} to remove.")
    estate = Estate.model_validate(snapshot.to_dict())

    # Deferred: importing at module scope would make membership.py depend on
    # models it otherwise has no use for, and this is the only caller.
    from models import Item, Message

    def _count(collection: str, limit: int = 1) -> int:
        return len(
            db.collection(collection)
            .where(filter=gcf.FieldFilter("estate_id", "==", estate_id))
            .limit(limit)
            .get()
        )

    blocking: list[str] = []
    if _count(Item.COLLECTION):
        blocking.append("belongings in it")
    if _count(Message.COLLECTION):
        blocking.append("messages in it")

    others = [
        m
        for m in list_memberships(estate_id)
        if m.user_id != executor_user_id
    ]
    if others:
        pending = sum(1 for m in others if m.accepted_at is None)
        blocking.append(
            f"{len(others)} other {'person' if len(others) == 1 else 'people'}"
            + (f" ({pending} still invited)" if pending else "")
        )

    if blocking:
        raise MembershipError(
            f'"{estate.name}" has ' + ", and ".join(blocking) + ". "
            "Steward only removes an estate that never had anything in it — "
            "nothing here gets deleted out from under a family."
        )

    batch = db.batch()
    batch.delete(estate_ref)
    batch.delete(
        db.collection(EstateMembership.COLLECTION).document(
            membership_id(estate_id, executor_user_id)
        )
    )
    batch.commit()
    return estate


def estates_for_user(user_id: str) -> list[tuple[Estate, MembershipRole]]:
    """Every estate this person belongs to, with the role they hold there.

    Accepted memberships only — a pending invite grants no role, which is the
    same rule `get_role()` applies, so an unaccepted invitation must not make an
    estate look like somewhere you can already go.

    Ordered by when the estate was created, so "the first one" is stable rather
    than whatever Firestore returns first.
    """
    db = get_db()
    snapshots = (
        db.collection(EstateMembership.COLLECTION)
        .where(filter=gcf.FieldFilter("user_id", "==", user_id))
        .get()
    )
    memberships = [EstateMembership.model_validate(s.to_dict()) for s in snapshots]
    accepted = [m for m in memberships if m.accepted_at is not None]
    if not accepted:
        return []

    refs = [
        db.collection(Estate.COLLECTION).document(m.estate_id) for m in accepted
    ]
    estates = {
        s.id: Estate.model_validate(s.to_dict()) for s in db.get_all(refs) if s.exists
    }
    pairs = [
        (estates[m.estate_id], m.role) for m in accepted if m.estate_id in estates
    ]
    return sorted(pairs, key=lambda pair: pair[0].created_at)


def pending_invitations_for_user(user_id: str) -> list[tuple[Estate, MembershipRole]]:
    """Estates this person has been asked into but has not accepted yet.

    The exact complement of `estates_for_user`, and it exists because nothing
    else could answer the question. `/me/estates` returns accepted memberships
    only — correctly, since a pending invite is not somewhere you can go — and
    `GET /me` can only report `invite_pending` for an estate *you already name*.
    So a browser holding a freshly invited account had no way to find out which
    estate had invited it, and an invitation nobody can discover is an
    invitation nobody can accept.

    Ordered by when the invitation was sent: if two arrived, the first one asked
    is the first one answered.
    """
    db = get_db()
    snapshots = (
        db.collection(EstateMembership.COLLECTION)
        .where(filter=gcf.FieldFilter("user_id", "==", user_id))
        .get()
    )
    memberships = [EstateMembership.model_validate(s.to_dict()) for s in snapshots]
    pending = sorted(
        (m for m in memberships if m.accepted_at is None),
        key=lambda m: m.invited_at,
    )
    if not pending:
        return []

    refs = [db.collection(Estate.COLLECTION).document(m.estate_id) for m in pending]
    estates = {
        s.id: Estate.model_validate(s.to_dict()) for s in db.get_all(refs) if s.exists
    }
    # An invitation to an estate that has since been removed is not an
    # invitation — dropped rather than reported, so nothing offers a door into
    # something that isn't there.
    return [(estates[m.estate_id], m.role) for m in pending if m.estate_id in estates]


def invite_to_estate(
    estate_id: str, email: str, role: MembershipRole
) -> EstateMembership:
    """Invite `email` to `estate_id` as `role`; accepted_at stays null (pending).

    The invitee must already have a Firebase Auth account — call
    `create_auth_user` first. Re-inviting someone who has already accepted is
    left alone (their acceptance is not silently revoked); re-inviting a
    still-pending member refreshes invited_at.
    """
    get_app()
    role = MembershipRole(role)

    try:
        record = auth.get_user_by_email(email)
    except auth.UserNotFoundError as exc:
        raise MembershipError(
            f"No Firebase Auth user for {email} — create the account before inviting."
        ) from exc

    db = get_db()
    doc_ref = db.collection(EstateMembership.COLLECTION).document(
        membership_id(estate_id, record.uid)
    )

    existing = doc_ref.get()
    if existing.exists and existing.to_dict().get("accepted_at") is not None:
        return EstateMembership.model_validate(existing.to_dict())

    membership = EstateMembership(
        id=doc_ref.id,
        estate_id=estate_id,
        user_id=record.uid,
        role=role,
        accepted_at=None,
    )
    doc_ref.set(
        {
            "id": membership.id,
            "estate_id": membership.estate_id,
            "user_id": membership.user_id,
            "role": membership.role.value,
            "invited_at": membership.invited_at,
            "accepted_at": None,
        }
    )
    return membership


def accept_invite(estate_id: str, user_id: str) -> EstateMembership:
    """Mark the pending invite for (estate_id, user_id) as accepted.

    Idempotent: accepting twice keeps the first accepted_at.
    """
    db = get_db()
    doc_ref = db.collection(EstateMembership.COLLECTION).document(
        membership_id(estate_id, user_id)
    )

    snapshot = doc_ref.get()
    if not snapshot.exists:
        raise MembershipError(
            f"No invite for user {user_id} on estate {estate_id} to accept."
        )

    data = snapshot.to_dict()
    if data.get("accepted_at") is None:
        doc_ref.update({"accepted_at": gcf.SERVER_TIMESTAMP})
        data = doc_ref.get().to_dict()

    return EstateMembership.model_validate(data)


def get_membership(estate_id: str, user_id: str) -> Optional[EstateMembership]:
    """The raw membership record, accepted or still pending; None if never invited."""
    snapshot = (
        get_db()
        .collection(EstateMembership.COLLECTION)
        .document(membership_id(estate_id, user_id))
        .get()
    )
    if not snapshot.exists:
        return None
    return EstateMembership.model_validate(snapshot.to_dict())


def list_memberships(estate_id: str) -> list[EstateMembership]:
    """Everyone invited to this estate, accepted or still pending.

    Ordered by when they were invited, so the executor reads it as the history
    of who they asked and in what order. A pending row is a real answer, not a
    missing one — `accepted_at is None` is the whole of "hasn't come in yet".
    """
    snapshots = (
        get_db()
        .collection(EstateMembership.COLLECTION)
        .where(filter=gcf.FieldFilter("estate_id", "==", estate_id))
        .get()
    )
    memberships = [EstateMembership.model_validate(s.to_dict()) for s in snapshots]
    return sorted(memberships, key=lambda m: m.invited_at)


def get_role(
    uid: str, estate_id: str, include_pending: bool = False
) -> Optional[MembershipRole]:
    """The caller's role on `estate_id`, or None if they have none.

    A pending invite grants no role by default — an unaccepted invitee is not
    yet a member. Pass include_pending=True to see the invited-but-not-accepted
    role (for rendering an invite screen, not for authorization).
    """
    membership = get_membership(estate_id, uid)
    if membership is None:
        return None
    if membership.accepted_at is None and not include_pending:
        return None
    return membership.role


def require_role(
    uid: str, estate_id: str, *allowed: MembershipRole
) -> MembershipRole:
    """Role-check for API handlers: return the caller's role or raise.

    Passing no `allowed` roles means "any accepted member".
    """
    role = get_role(uid, estate_id)
    if role is None:
        raise MembershipError(f"User {uid} is not an accepted member of {estate_id}.")
    if allowed and role not in allowed:
        expected = " or ".join(r.value for r in allowed)
        raise MembershipError(
            f"User {uid} is {role.value} on {estate_id}; {expected} required."
        )
    return role
