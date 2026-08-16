"""Telling people the two things they'd otherwise only find by opening the app.

Steward is multi-user, and until now nothing ever reached out except the
invitation. The question a family actually asks is "how would my sister know
this happened?" — and there are exactly two moments where the honest answer had
to be "she wouldn't":

  1. **An item became contested.** Two people's interests just collided. This is
     the single most important message the product sends.
  2. **A resolution was recorded.** Everyone who asked hears what was decided —
     *including the people who didn't get it*, which matters at least as much.

Not a notification system. Two triggers, deliberately, because a general one
would need preferences and an unsubscribe to be honest, and half of that is
worse than none (see the note at the bottom of this file).

**A courtesy layer on top of real state, never a dependency of it.** Every
function here swallows its own failures: the mediation message has already
posted and the resolution has already been recorded by the time any of this
runs, and losing that work over a mail server would be indefensible. All sending
goes through `mailer.send`, which is where SMTP is spoken.
"""

import logging
from typing import Iterable, NamedTuple, Optional

from firebase_app import get_db
from mailer import send
from models import Item, User

logger = logging.getLogger(__name__)

# The app has no public URL yet — nothing is deployed. When STEWARD_APP_URL is
# set, the emails carry a link straight to the item; when it isn't, they simply
# don't, rather than printing a dead localhost address at someone.
from os import environ


class Recipient(NamedTuple):
    user_id: str
    display_name: str
    email: str


def _item_link(item_id: str) -> Optional[str]:
    base = environ.get("STEWARD_APP_URL", "").strip().rstrip("/")
    return f"{base}/items/{item_id}" if base else None


def recipients_for(user_ids: Iterable[str]) -> list[Recipient]:
    """Name and email for each person, skipping anyone we can't write to.

    The agent user has no email and no Auth account, so it falls out here
    naturally rather than needing to be special-cased at every call site.
    """
    db = get_db()
    out: list[Recipient] = []
    for user_id in dict.fromkeys(user_ids):
        snapshot = db.collection(User.COLLECTION).document(user_id).get()
        data = snapshot.to_dict() if snapshot.exists else None
        email = (data or {}).get("email", "").strip()
        if not email:
            continue
        out.append(Recipient(user_id, (data or {}).get("display_name") or "there", email))
    return out


def _thing(item: Item) -> str:
    """What to call the item in a sentence — its category, plus era if there is one."""
    era = (item.ai_est_era_or_brand or "").strip()
    return f"{item.ai_category} ({era})" if era else item.ai_category


def _footer(item_id: str) -> str:
    link = _item_link(item_id)
    return f"\n\nYou can see it here:\n{link}\n" if link else "\n"


# --- 1. an item became contested -------------------------------------------

def notify_contested(
    item: Item, claimant_ids: list[str], mediation_text: str
) -> list[tuple[str, bool]]:
    """Email everyone who has asked for an item that has just become contested.

    **The mediation message is the body.** It was written for exactly this
    moment, in exactly this voice — wrapping it in "You have a new notification"
    would replace something a person can act on with an envelope. The email says
    what Steward said, to the people it was said about.

    Returns (email, sent) per recipient. Never raises.
    """
    try:
        people = recipients_for(claimant_ids)
    except Exception:  # noqa: BLE001 — a courtesy that failed, not a failed claim
        logger.exception("could not look up claimants for %s", item.id)
        return []

    results = []
    for person in people:
        body = (
            f"Hello {person.display_name.split(' ')[0]},\n\n"
            f"More than one of you has asked for the {_thing(item)}, so Steward "
            "has left a note about it for the family:\n\n"
            f"{mediation_text}"
            f"{_footer(item.id)}"
            "\nNothing has to be decided today.\n\n— Steward\n"
        )
        try:
            result = send(
                person.email,
                subject=f"You and someone else have both asked for the {item.ai_category}",
                text=body,
                kind="contested",
            )
        except Exception:  # noqa: BLE001 — belt and braces; send() already swallows
            logger.exception("contested email to %s failed", person.email)
            results.append((person.email, False))
            continue
        results.append((person.email, result.sent))
    return results


# --- 2. a resolution was recorded ------------------------------------------

# How each resolution type reads to someone who was not in the room.
_OUTCOME = {
    "assigned_to_claimant": "it's going to {to}",
    "rotation": "you're going to share it, in turns — {to} has it first",
    "outside_appraisal": "it's going to be valued by someone outside the family first",
    "executor_override": "{by} has settled it",
}


def notify_resolved(
    item: Item,
    claimant_ids: list[str],
    resolution_type: str,
    resolved_by_name: str,
    resolved_to_name: Optional[str],
    notes: str = "",
) -> list[tuple[str, bool]]:
    """Email everyone who asked for an item about how it was settled.

    **Everyone who asked, not only the person who got it.** Being told the thing
    you wanted has gone to your sister is the harder message and the more
    necessary one; a product that only writes to the winner is telling people
    they matter in proportion to whether they got what they wanted.

    The same words go to all of them. Writing a softer version for whoever
    missed out would mean the family holds two different accounts of the same
    decision, which is exactly the thing this is supposed to prevent.

    Returns (email, sent) per recipient. Never raises.
    """
    try:
        people = recipients_for(claimant_ids)
    except Exception:  # noqa: BLE001
        logger.exception("could not look up claimants for %s", item.id)
        return []

    outcome = _OUTCOME.get(resolution_type, "{by} has settled it").format(
        to=resolved_to_name or "someone", by=resolved_by_name
    )
    note_line = f'\n{resolved_by_name} added: "{notes.strip()}"\n' if notes.strip() else ""

    results = []
    for person in people:
        body = (
            f"Hello {person.display_name.split(' ')[0]},\n\n"
            f"The {_thing(item)} has been settled — {outcome}.\n"
            f"{note_line}"
            f"{_footer(item.id)}"
            "\nIf that doesn't sit right, say so in the thread — it's a record of "
            "a decision, not the end of a conversation.\n\n— Steward\n"
        )
        try:
            result = send(
                person.email,
                subject=f"The {item.ai_category} has been settled",
                text=body,
                kind="resolved",
            )
        except Exception:  # noqa: BLE001
            logger.exception("resolution email to %s failed", person.email)
            results.append((person.email, False))
            continue
        results.append((person.email, result.sent))
    return results


# --- what this deliberately does not do ------------------------------------
#
# There are **no notification preferences and no unsubscribe** here, and that is
# a real gap rather than an oversight. Both would need somewhere to live in the
# data model (a field on EstateMembership, or a table of its own), a UI to set
# them, and an unauthenticated route to honour an unsubscribe link. A half-built
# version — say, an unsubscribe link that goes nowhere — would be worse than
# none, because it would promise something the system cannot do.
#
# Two triggers, both about a specific decision on a specific belonging, is a
# volume a family will not want to switch off. That stops being true the moment
# anything more chatty is added, and the preference work has to land first.
