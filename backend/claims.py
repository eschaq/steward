"""Recording claims and recomputing the claimed/contested status of an item.

Claim's shape is fixed by docs/estate-agent-data-model.md: one row per claim,
with **no uniqueness constraint** on (item_id, user_id). That is deliberate —
per the RDD's failure-handling section, two beneficiaries claiming the same item
at the same moment should both land in the collection. 2+ claimants already
*means* contested by design, so there is nothing here to race-prevent.

Status is therefore derived from the claims, never asserted by the caller:
1 distinct claiming user -> `claimed`, 2+ distinct claiming users -> `contested`.
"""

from enum import Enum
from typing import Optional

from google.cloud.firestore_v1.base_query import FieldFilter

from firebase_app import get_db
from messages import post_contested_mediation
from models import Claim, Item, ItemStatus

# Statuses this module owns. An item that has been resolved or routed has moved
# past claiming, and a needs_clarification item hasn't been identified well
# enough to claim meaningfully — recompute leaves all three alone rather than
# quietly dragging them backwards into the claim triad.
CLAIMABLE_STATUSES = frozenset(
    {ItemStatus.UNCLAIMED, ItemStatus.CLAIMED, ItemStatus.CONTESTED}
)


class ClaimError(Exception):
    """A claim could not be recorded.

    Raised rather than swallowed — a claim that silently goes nowhere is exactly
    the failure mode CLAUDE.md rules out.
    """


def _to_firestore(model) -> dict:
    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in model.model_dump().items()
    }


def get_claims_for_item(item_id: str) -> list[Claim]:
    """Every claim on `item_id`, oldest first.

    Single-field equality filter, so Firestore's automatic index covers it — no
    composite index to deploy.
    """
    snapshots = (
        get_db()
        .collection(Claim.COLLECTION)
        .where(filter=FieldFilter("item_id", "==", item_id))
        .get()
    )
    claims = [Claim.model_validate(s.to_dict()) for s in snapshots]
    return sorted(claims, key=lambda c: c.claimed_at)


def count_claims(item_id: str) -> int:
    """Total claim documents on `item_id`, duplicates from one user included."""
    return len(get_claims_for_item(item_id))


def claimant_ids_for_item(item_id: str) -> list[str]:
    """The distinct users who claimed `item_id`, in the order they spoke up.

    Order matters: the mediation message names people in it. Shared with the ADK
    tool wrapper so both derive claimants the same way.
    """
    return list(dict.fromkeys(claim.user_id for claim in get_claims_for_item(item_id)))


def count_distinct_claimants(item_id: str) -> int:
    """How many *different* users have claimed `item_id`.

    This, not the raw document count, is what drives status: one person claiming
    twice is still one claimant, and must not tip an item into `contested`.
    """
    return len({claim.user_id for claim in get_claims_for_item(item_id)})


def status_for_claimant_count(claimant_count: int) -> ItemStatus:
    """The status implied by a distinct-claimant count."""
    if claimant_count == 0:
        return ItemStatus.UNCLAIMED
    if claimant_count == 1:
        return ItemStatus.CLAIMED
    return ItemStatus.CONTESTED


def recompute_item_status(item_id: str) -> ItemStatus:
    """Re-derive `item_id`'s status from its claims and persist it.

    Returns the item's status after the call. Items sitting in `resolved`,
    `routed`, or `needs_clarification` are returned unchanged — see
    CLAIMABLE_STATUSES.

    On the *transition* into `contested` — and only then — the agent posts its
    mediating suggestion to the Message Center. Recomputing an item that was
    already contested changes nothing and says nothing.
    """
    doc_ref = get_db().collection(Item.COLLECTION).document(item_id)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        raise ClaimError(f"No item {item_id} to recompute status for.")

    data = snapshot.to_dict()
    current = ItemStatus(data["status"])
    if current not in CLAIMABLE_STATUSES:
        return current

    # Claimant order follows claimed_at, so the mediation message names people
    # in the order they actually spoke up.
    claimant_ids = claimant_ids_for_item(item_id)

    new_status = status_for_claimant_count(len(claimant_ids))
    if new_status == current:
        return new_status

    doc_ref.update({"status": new_status.value})

    if new_status is ItemStatus.CONTESTED:
        post_contested_mediation(data["estate_id"], item_id, claimant_ids)

    return new_status


def record_claim(
    item_id: str, user_id: str, comment: Optional[str] = None
) -> tuple[Claim, ItemStatus]:
    """Record a beneficiary's claim on an item and recompute the item's status.

    Returns the stored Claim and the item's status afterwards.

    Every call writes a new document — including a repeat claim from a user who
    has already claimed this item. A second claim is a real event (usually an
    added or revised comment) and dropping it would be a silent guess about what
    the person meant. Because status counts *distinct* claimants, re-claiming
    never escalates an item to `contested` on its own.
    """
    db = get_db()
    if not db.collection(Item.COLLECTION).document(item_id).get().exists:
        raise ClaimError(f"No item {item_id} to claim.")

    doc_ref = db.collection(Claim.COLLECTION).document()
    claim = Claim(id=doc_ref.id, item_id=item_id, user_id=user_id, comment=comment)
    doc_ref.set(_to_firestore(claim))

    return claim, recompute_item_status(item_id)
