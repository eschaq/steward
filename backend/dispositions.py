"""The executor's final call on a resolved item: a Disposition row, and the log of it.

Disposition is *the seam* the data model doc describes — the point every item
passes through once resolved, and the only thing Tier 2 (marketplace listings)
and Tier 3 (auction batching) ever attach to. Recording a decision here writes
two documents together:

  * the **Disposition** row — where the item is actually headed, `pending` until
    someone acts on it
  * the **OverrideLog** entry — so `overrides.py` can weight this estate's future
    suggestions by what the executor actually chose, agreements included

Both are written in one batch: a decision that logged but didn't route, or routed
but didn't log, would be worse than one that failed outright.

Gates match resolutions.py: executor only, and only on an item that has actually
been resolved. A disposition decided before the family has settled who gets the
item would be answering the wrong question.
"""

from typing import Optional

from google.cloud import firestore as gcf

from firebase_app import get_db
from membership import MembershipRole, require_role
from models import (
    Disposition,
    DispositionChannel,
    DispositionStatus,
    Item,
    ItemStatus,
    OverrideLog,
    SuggestedDisposition,
)
from overrides import build_override_log, override_log_document, override_log_id

# The executor picks a disposition; this is the channel it routes to.
# `sell_auction_bulk` is Tier 3 — it exists on the enum so the entity's shape
# never changes when batching lands, but nothing in Tier 1 routes to it.
CHANNEL_FOR_CHOICE = {
    SuggestedDisposition.DISCARD: DispositionChannel.DISCARD,
    SuggestedDisposition.DONATE: DispositionChannel.DONATE,
    SuggestedDisposition.SELL: DispositionChannel.SELL_MARKETPLACE,
}


class DispositionError(Exception):
    """The item isn't ready for a disposition decision, or the choice is not one.

    Authorization failures raise `MembershipError` from membership.py instead,
    so "you may not do this" stays distinguishable from "this can't be done yet".
    """


def disposition_id(item_id: str) -> str:
    """Deterministic document id: one disposition per item.

    Matches `override_log_id`, so an executor who revises their decision replaces
    both documents and the two never drift apart.
    """
    return f"disposition__{item_id}"


def get_disposition_decision(item_id: str) -> Optional[OverrideLog]:
    """The logged decision for an item, or None if none has been made."""
    snapshot = (
        get_db().collection(OverrideLog.COLLECTION).document(override_log_id(item_id)).get()
    )
    if not snapshot.exists:
        return None
    return OverrideLog.model_validate(snapshot.to_dict())


# What comes after what. `completed` is terminal — there is no "un-donate".
NEXT_STATUS = {
    DispositionStatus.PENDING: DispositionStatus.IN_PROGRESS,
    DispositionStatus.IN_PROGRESS: DispositionStatus.COMPLETED,
}


def advance_disposition(item_id: str, uid: str) -> Disposition:
    """Move a disposition one step along: pending -> in_progress -> completed.

    Executor only. One step per call, deliberately — each step corresponds to
    something that actually happened in the world (the charity shop has it now;
    the charity shop has taken it), and skipping to the end would record an
    event nobody witnessed.

    **The item's status becomes `routed` at in_progress and stays there.** This
    is the only place anything sets `routed`, and nothing else in the codebase
    reads it: the three status gates (CLAIMABLE_STATUSES, RESOLVABLE_STATUSES,
    SUGGESTION_ELIGIBLE_STATUSES) are allow-lists that exclude it, so a routed
    item is already out of claiming, resolving and suggestion recompute.

    **Completion does not get its own Item status**, and that is a deliberate
    reading of the data model doc rather than an omission. Disposition is given
    its own `status` and `completed_at` precisely so the fulfilment lifecycle
    lives there; the doc's own note says every tier's detail "lives in tables
    that reference Disposition, never in Item/Claim/Comment/Resolution
    themselves". An eighth Item status meaning "gone" would push disposition
    detail back up into Item — the exact thing the seam exists to prevent — and
    would create a second source of truth that could disagree with
    `Disposition.completed_at`. Item.status answers "where did this land in the
    claim flow"; Disposition answers "and has it actually gone yet".

    Raises `MembershipError` if the caller is not the executor of this item's
    estate, and `DispositionError` if there is no disposition yet or it is
    already completed. Nothing is written in either case.
    """
    db = get_db()
    snapshot = db.collection(Item.COLLECTION).document(item_id).get()
    if not snapshot.exists:
        raise DispositionError(f"No item {item_id} to move along.")
    item = Item.model_validate(snapshot.to_dict())

    # Authorization first, so a non-executor isn't told about the item's state.
    require_role(uid, item.estate_id, MembershipRole.EXECUTOR)

    disposition = get_disposition(item_id)
    if disposition is None:
        raise DispositionError(
            f"Item {item_id} has no disposition yet — the executor decides where "
            "it goes before there is anything to move along."
        )

    if disposition.status not in NEXT_STATUS:
        raise DispositionError(
            f"Item {item_id} is already {disposition.status.value} — there is "
            "nothing further to mark."
        )

    nxt = NEXT_STATUS[disposition.status]
    updates: dict = {"status": nxt.value}
    if nxt is DispositionStatus.COMPLETED:
        updates["completed_at"] = gcf.SERVER_TIMESTAMP

    batch = db.batch()
    batch.update(
        db.collection(Disposition.COLLECTION).document(disposition.id), updates
    )
    # Only on the first step. At completion the item is already routed, and
    # rewriting the same value would be a write that says nothing.
    if nxt is DispositionStatus.IN_PROGRESS:
        batch.update(
            db.collection(Item.COLLECTION).document(item_id),
            {"status": ItemStatus.ROUTED.value},
        )
    batch.commit()

    return get_disposition(item_id)


def get_disposition(item_id: str) -> Optional[Disposition]:
    """Where the item is headed, or None if no decision has been made."""
    snapshot = (
        get_db().collection(Disposition.COLLECTION).document(disposition_id(item_id)).get()
    )
    if not snapshot.exists:
        return None
    return Disposition.model_validate(snapshot.to_dict())


def record_disposition_decision(
    item_id: str,
    executor_chosen_disposition: SuggestedDisposition,
    uid: str,
) -> tuple[OverrideLog, Disposition]:
    """Record the executor's final call on what happens to a resolved item.

    Writes two documents in one batch, and returns both:

      * a **Disposition** row routing the item to its channel, `pending`
      * an **OverrideLog** entry so future suggestions for this estate and
        category are weighted by it — including when the executor agreed with the
        agent. The data model's own example ("donated 4 of 5 sentimental items")
        counts total outcomes, so agreements have to be counted too, not just
        corrections.

    Raises `MembershipError` if the caller is not the executor of this item's
    estate, and `DispositionError` if the item isn't resolved yet or the choice
    isn't a real disposition. Nothing is written in either case.
    """
    choice = SuggestedDisposition(executor_chosen_disposition)

    db = get_db()
    snapshot = db.collection(Item.COLLECTION).document(item_id).get()
    if not snapshot.exists:
        raise DispositionError(f"No item {item_id} to decide a disposition for.")

    item = Item.model_validate(snapshot.to_dict())

    # Authorization first, so a non-executor isn't told about the item's state.
    require_role(uid, item.estate_id, MembershipRole.EXECUTOR)

    if item.status is not ItemStatus.RESOLVED:
        raise DispositionError(
            f"Cannot decide a disposition for item {item_id}: it is "
            f"{item.status.value}, and only a resolved item is ready for one."
        )

    # "Uncertain" is the absence of a decision — there is no channel to route it
    # to, and logging it would teach the estate's history that hesitation is a
    # preference. Deferring is a valid thing for an executor to do; it just isn't
    # this function, so say so instead of picking something on their behalf.
    if choice not in CHANNEL_FOR_CHOICE:
        raise DispositionError(
            f"'{choice.value}' is not a disposition — the executor has to choose "
            f"{', '.join(c.value for c in CHANNEL_FOR_CHOICE)}."
        )

    entry = build_override_log(
        estate_id=item.estate_id,
        item_id=item.id,
        item_category=item.ai_category,
        ai_suggested_disposition=item.suggested_disposition,
        executor_chosen_disposition=choice,
    )
    disposition = Disposition(
        id=disposition_id(item.id),
        item_id=item.id,
        channel=CHANNEL_FOR_CHOICE[choice],
        status=DispositionStatus.PENDING,
        completed_at=None,
    )

    # One batch: a decision that logged but didn't route, or routed but didn't
    # log, would leave the estate's history and the item's fate disagreeing.
    batch = db.batch()
    batch.set(
        db.collection(OverrideLog.COLLECTION).document(entry.id),
        override_log_document(entry),
    )
    batch.set(
        db.collection(Disposition.COLLECTION).document(disposition.id),
        {
            "id": disposition.id,
            "item_id": disposition.item_id,
            "channel": disposition.channel.value,
            "status": disposition.status.value,
            "completed_at": disposition.completed_at,
        },
    )
    batch.commit()

    return entry, disposition
