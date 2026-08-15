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
from models import EstateMembership, MembershipRole, RoleType, User


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
