"""PLACEHOLDER for the Disposition entity — currently only the OverrideLog write.

**This is not the Disposition entity.** The data model doc defines Disposition as
a real Tier 1 row (id, item_id, channel, status, completed_at) and calls it *the
seam* — the point every item passes through once resolved, and the only thing
Tier 2 (marketplace listings) and Tier 3 (auction batching) ever attach to.
None of that is built here.

What this module does today is the one piece the adaptive loop can't wait for:
capture the executor's finalized choice so `overrides.py` has something to learn
from. When the real Disposition entity lands, `record_disposition_decision`
becomes the function that writes the Disposition row *and* logs the override —
the OverrideLog write below moves inside it rather than being replaced by it.

Gates match resolutions.py: executor only, and only on an item that has actually
been resolved. A disposition decided before the family has settled who gets the
item would be answering the wrong question.
"""

from typing import Optional

from firebase_app import get_db
from membership import MembershipRole, require_role
from models import Item, ItemStatus, OverrideLog, SuggestedDisposition
from overrides import override_log_id, write_override_log


class DispositionError(Exception):
    """The item isn't ready for a disposition decision, or the choice is not one.

    Authorization failures raise `MembershipError` from membership.py instead,
    so "you may not do this" stays distinguishable from "this can't be done yet".
    """


def get_disposition_decision(item_id: str) -> Optional[OverrideLog]:
    """The logged decision for an item, or None if none has been made."""
    snapshot = (
        get_db().collection(OverrideLog.COLLECTION).document(override_log_id(item_id)).get()
    )
    if not snapshot.exists:
        return None
    return OverrideLog.model_validate(snapshot.to_dict())


def record_disposition_decision(
    item_id: str,
    executor_chosen_disposition: SuggestedDisposition,
    uid: str,
) -> OverrideLog:
    """Record the executor's final call on what happens to a resolved item.

    Logs it to `override_logs` so future suggestions for this estate and category
    are weighted by it — including when the executor agreed with the agent. The
    data model's own example ("donated 4 of 5 sentimental items") counts total
    outcomes, so agreements have to be counted too, not just corrections.

    Raises `MembershipError` if the caller is not the executor of this item's
    estate, and `DispositionError` if the item isn't resolved yet or the choice
    isn't a real disposition. Nothing is written in either case.
    """
    choice = SuggestedDisposition(executor_chosen_disposition)

    snapshot = get_db().collection(Item.COLLECTION).document(item_id).get()
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

    # "Uncertain" is the absence of a decision. Logging it would teach the estate's
    # history that hesitation is a preference.
    if choice is SuggestedDisposition.UNCERTAIN:
        raise DispositionError(
            f"'{choice.value}' is not a disposition — the executor has to choose "
            "discard, donate, or sell."
        )

    return write_override_log(
        estate_id=item.estate_id,
        item_id=item.id,
        item_category=item.ai_category,
        ai_suggested_disposition=item.suggested_disposition,
        executor_chosen_disposition=choice,
    )
