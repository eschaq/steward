"""Resolving a claimed or contested item, and flipping it to `resolved`.

Per docs/estate-agent-data-model.md, a Resolution is the executor's decision
about who an item goes to and why. It moves the item out of the claim triad and
makes it eligible for Disposition — the seam Tier 2 and Tier 3 attach at.

Two gates, and both raise rather than shrug:

  * **Authorization** — only the executor of the item's estate may resolve it.
    Enforced with `membership.require_role`, so this module has no second,
    divergent idea of what an executor is.
  * **State** — there has to be something to resolve. An `unclaimed` item has no
    decision waiting on it, and silently "resolving" it would strand it outside
    the claim flow with nobody having asked for it.
"""

from enum import Enum
from typing import Optional

from claims import get_claims_for_item
from firebase_app import get_db
from membership import MembershipRole, require_role
from messages import display_names_for
from notify import notify_resolved
from models import Item, ItemStatus, Resolution, ResolutionType

# An item can only be resolved out of the claim triad's two decided states.
# `unclaimed` has nothing to decide, `needs_clarification` isn't identified yet,
# and `resolved`/`routed` are already past this point.
RESOLVABLE_STATUSES = frozenset({ItemStatus.CLAIMED, ItemStatus.CONTESTED})

# Where naming a recipient is the whole point of the decision.
TYPES_REQUIRING_RECIPIENT = frozenset(
    {ResolutionType.ASSIGNED_TO_CLAIMANT, ResolutionType.ROTATION}
)


class ResolutionError(Exception):
    """The item is not in a state that can be resolved, or the decision is incoherent.

    Authorization failures raise `MembershipError` from membership.py instead —
    the caller should be able to tell "you may not do this" apart from "this
    can't be done yet".
    """


def _to_firestore(model) -> dict:
    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in model.model_dump().items()
    }


def resolution_id(item_id: str) -> str:
    """Deterministic document id: one resolution per item.

    The status gate already allows an item to be resolved exactly once, since
    `resolved` is outside RESOLVABLE_STATUSES. Pinning the id makes that
    structural instead of merely emergent.
    """
    return f"resolution__{item_id}"


def get_resolution(item_id: str) -> Optional[Resolution]:
    """The item's resolution, or None if it hasn't been resolved."""
    snapshot = (
        get_db().collection(Resolution.COLLECTION).document(resolution_id(item_id)).get()
    )
    if not snapshot.exists:
        return None
    return Resolution.model_validate(snapshot.to_dict())


def resolve_item(
    item_id: str,
    resolved_by_user_id: str,
    resolution_type: ResolutionType,
    resolved_to_user_id: Optional[str] = None,
    notes: str = "",
) -> Resolution:
    """Record the executor's decision on `item_id` and flip it to `resolved`.

    Raises `MembershipError` if the caller is not the executor of this item's
    estate, and `ResolutionError` if the item isn't in a resolvable state or the
    decision doesn't hold together. Nothing is written in either case.
    """
    resolution_type = ResolutionType(resolution_type)

    db = get_db()
    item_ref = db.collection(Item.COLLECTION).document(item_id)
    snapshot = item_ref.get()
    if not snapshot.exists:
        raise ResolutionError(f"No item {item_id} to resolve.")

    data = snapshot.to_dict()
    status = ItemStatus(data["status"])

    # Authorization before state, so a non-executor learns they may not do this
    # rather than learning about the item's internal state first.
    require_role(resolved_by_user_id, data["estate_id"], MembershipRole.EXECUTOR)

    if status not in RESOLVABLE_STATUSES:
        if status is ItemStatus.UNCLAIMED:
            detail = "nobody has claimed it, so there is nothing to resolve yet"
        elif status is ItemStatus.RESOLVED:
            detail = "it has already been resolved"
        elif status is ItemStatus.NEEDS_CLARIFICATION:
            detail = "it still needs to be identified"
        else:
            detail = f"it is {status.value}"
        raise ResolutionError(f"Cannot resolve item {item_id}: {detail}.")

    claimant_ids = {claim.user_id for claim in get_claims_for_item(item_id)}

    if resolution_type in TYPES_REQUIRING_RECIPIENT:
        if not resolved_to_user_id:
            raise ResolutionError(
                f"A {resolution_type.value} resolution has to name who the item "
                "goes to — resolved_to_user_id is required."
            )
        # Handing the item to someone who never asked for it is a different
        # decision, and the data model has a type for it: executor_override.
        if resolved_to_user_id not in claimant_ids:
            raise ResolutionError(
                f"User {resolved_to_user_id} did not claim item {item_id}, so this "
                f"is not a {resolution_type.value} — use executor_override instead."
            )

    resolution = Resolution(
        id=resolution_id(item_id),
        item_id=item_id,
        resolved_by_user_id=resolved_by_user_id,
        resolution_type=resolution_type,
        resolved_to_user_id=resolved_to_user_id,
        notes=notes,
    )
    db.collection(Resolution.COLLECTION).document(resolution.id).set(
        _to_firestore(resolution)
    )
    item_ref.update({"status": ItemStatus.RESOLVED.value})

    # Everyone who asked hears what was decided — including whoever didn't get
    # it. Best-effort and last: the resolution is recorded above and stands
    # whatever happens here.
    try:
        names = display_names_for(
            [resolved_by_user_id] + ([resolved_to_user_id] if resolved_to_user_id else [])
        )
        notify_resolved(
            item=Item.model_validate(item_ref.get().to_dict()),
            claimant_ids=sorted(claimant_ids),
            resolution_type=resolution_type.value,
            resolved_by_name=names.get(resolved_by_user_id, "The executor"),
            resolved_to_name=(
                names.get(resolved_to_user_id) if resolved_to_user_id else None
            ),
            notes=notes,
        )
    except Exception as exc:  # noqa: BLE001 — a courtesy, never a gate
        print(f"  ! could not email the claimants about {item_id}: {exc}")

    return resolution
