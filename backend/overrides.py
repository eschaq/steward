"""The adaptive suggestion loop: learn each estate's disposition habits, apply them.

This is the persistent-memory mechanic the Collaborative Partner track requires.
Every finalized executor decision lands in `override_logs`; before suggesting a
disposition for a new item, the agent counts this estate's past decisions in the
same category and leans that way, saying plainly why.

**Simple category-based counting, deliberately.** No embeddings, no vector
search, no semantic retrieval — an explicit non-goal per CLAUDE.md and the
hackathon's own cost-saving guidance. `item_category` is denormalized onto the
log row precisely so this stays one query and a `Counter`.

Failure handling follows the RDD: with no history for a category, the agent
returns the classifier's read unchanged and says "no pattern yet for this
estate". It never fabricates a lean out of nothing, and never quietly pretends
it had one.
"""

from collections import Counter
from enum import Enum
from typing import Optional

from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel

from firebase_app import get_db
from models import OverrideLog, SuggestedDisposition

# How many past decisions in a category before the agent will lean on them. One
# is thin, and the reason text says so out loud rather than overstating it.
MIN_HISTORY_FOR_PATTERN = 1

# The phrase the RDD asks for verbatim when there is nothing to go on.
NO_PATTERN_SIGNAL = "no pattern yet for this estate"

_PAST_TENSE = {
    SuggestedDisposition.DISCARD: "discarded",
    SuggestedDisposition.DONATE: "donated",
    SuggestedDisposition.SELL: "sold",
    SuggestedDisposition.UNCERTAIN: "left undecided",
}


class DispositionSuggestion(BaseModel):
    """What the agent suggests for an item, and the honest account of why.

    Not a persisted entity — it never goes to Firestore, so it lives here rather
    than in models.py, which mirrors the data model doc one-for-one.
    """

    suggested_disposition: SuggestedDisposition
    # Plain-language, family-readable. Shown alongside the suggestion.
    reason: str
    # False means the suggestion is the classifier's read, unadapted.
    has_pattern: bool
    # Past decisions in this category that match the suggestion, and in total.
    matching_count: int = 0
    history_count: int = 0
    # Passed through untouched — the override log weights the disposition, never
    # the classifier's confidence in what the thing is.
    ai_classification_confidence: Optional[float] = None


def _to_firestore(model) -> dict:
    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in model.model_dump().items()
    }


def override_log_id(item_id: str) -> str:
    """Deterministic document id: one logged decision per item.

    An executor who revisits a decision should replace their earlier one, not
    have both counted — a changed mind would otherwise weight the estate's
    history twice.
    """
    return f"override__{item_id}"


def build_override_log(
    estate_id: str,
    item_id: str,
    item_category: str,
    ai_suggested_disposition: SuggestedDisposition,
    executor_chosen_disposition: SuggestedDisposition,
) -> OverrideLog:
    """The log entry for one finalized decision, unwritten.

    Split out from the write so `dispositions.py` can commit it in the same batch
    as the Disposition row — the two have to land together or not at all.
    """
    return OverrideLog(
        id=override_log_id(item_id),
        estate_id=estate_id,
        item_id=item_id,
        item_category=item_category,
        ai_suggested_disposition=SuggestedDisposition(ai_suggested_disposition),
        executor_chosen_disposition=SuggestedDisposition(executor_chosen_disposition),
    )


def override_log_document(entry: OverrideLog) -> dict:
    """The Firestore-writable form of a log entry."""
    return _to_firestore(entry)


def write_override_log(
    estate_id: str,
    item_id: str,
    item_category: str,
    ai_suggested_disposition: SuggestedDisposition,
    executor_chosen_disposition: SuggestedDisposition,
) -> OverrideLog:
    """Record one finalized decision on its own. Called by dispositions.py."""
    entry = build_override_log(
        estate_id,
        item_id,
        item_category,
        ai_suggested_disposition,
        executor_chosen_disposition,
    )
    get_db().collection(OverrideLog.COLLECTION).document(entry.id).set(
        _to_firestore(entry)
    )
    return entry


def get_override_history(
    estate_id: str, item_category: Optional[str] = None
) -> list[OverrideLog]:
    """This estate's logged decisions, newest first, optionally one category only.

    Filters on `estate_id` in Firestore and on category in memory: a two-equality
    query would want a composite index, and an estate's decision log is small
    enough that fetching it whole costs less than an index to deploy and keep.
    """
    snapshots = (
        get_db()
        .collection(OverrideLog.COLLECTION)
        .where(filter=FieldFilter("estate_id", "==", estate_id))
        .get()
    )
    entries = [OverrideLog.model_validate(s.to_dict()) for s in snapshots]
    if item_category is not None:
        wanted = item_category.strip().lower()
        entries = [e for e in entries if e.item_category.strip().lower() == wanted]
    return sorted(entries, key=lambda e: e.created_at, reverse=True)


def _plural(category: str, count: int) -> str:
    """'4 kitchenware items' / 'the one kitchenware item'."""
    if count == 1:
        return f"the one {category} item"
    return f"{count} {category} items"


def suggest_disposition(
    estate_id: str,
    item_category: str,
    baseline: SuggestedDisposition = SuggestedDisposition.UNCERTAIN,
    ai_classification_confidence: Optional[float] = None,
    identified: bool = True,
) -> DispositionSuggestion:
    """What to suggest doing with an item, weighted by this estate's history.

    `baseline` is the classifier's own read, returned unchanged whenever there
    is no pattern to lean on. `identified=False` (an item that landed in
    `needs_clarification`) skips the lookup entirely — leaning on a category the
    agent isn't confident about would be applying a real pattern to a guess.
    """
    unadapted = DispositionSuggestion(
        suggested_disposition=baseline,
        reason="",
        has_pattern=False,
        ai_classification_confidence=ai_classification_confidence,
    )

    if not identified:
        unadapted.reason = (
            "I couldn't identify this one well enough to say what should happen "
            "to it — worth sorting out what it is first."
        )
        return unadapted

    category = (item_category or "").strip()
    history = get_override_history(estate_id, category) if category else []
    unadapted.history_count = len(history)

    if len(history) < MIN_HISTORY_FOR_PATTERN:
        unadapted.reason = (
            f"There's {NO_PATTERN_SIGNAL} — nothing else in {category or 'this category'} "
            "has been decided yet, so this is the classifier's read on its own."
        )
        return unadapted

    counts = Counter(entry.executor_chosen_disposition for entry in history)
    ranked = counts.most_common()

    # A dead heat is not a pattern. Saying so beats picking a side and dressing
    # it up as one.
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        split = ", ".join(
            f"{count} {_PAST_TENSE[disposition]}" for disposition, count in ranked
        )
        unadapted.reason = (
            f"This estate is evenly split on {category} so far ({split}), so "
            f"there's {NO_PATTERN_SIGNAL} to lean on. This is the classifier's "
            "read on its own."
        )
        return unadapted

    choice, matching = ranked[0]
    total = len(history)
    if matching == total:
        tally = f"has {_PAST_TENSE[choice]} {_plural(category, total)} so far"
    else:
        tally = f"has {_PAST_TENSE[choice]} {matching} of {_plural(category, total)} so far"

    return DispositionSuggestion(
        suggested_disposition=choice,
        reason=f"This estate {tally}, so I'm leaning {choice.value} here too.",
        has_pattern=True,
        matching_count=matching,
        history_count=total,
        ai_classification_confidence=ai_classification_confidence,
    )
