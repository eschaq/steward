"""The third agent behaviour: noticing when someone has shared a memory.

An estate is not only an inventory. Somewhere in the thread about a mantel
clock, one person says the thing that makes it a mantel clock *of theirs* — and
the moment that happens is the one moment a second person is most likely to say
theirs too, if anybody asks. Nobody asks. So Steward does, once.

**Outside the ADK dispatch, deliberately.** `agent.py`'s `TOOL_FOR_STATUS` maps
*status transitions* to behaviours, and that is precisely what makes the
clarify and mediate behaviours reliable: the backend detects the transition, so
they cannot be missed at the mercy of a sampling temperature. This one is
triggered by what a person chose to write, which is not a state the backend can
detect — the judgement *is* the model call. Forcing it into that table for
symmetry would misrepresent how it works. Same reasoning as `clarify.py`.

**Conservative on purpose.** A false positive — Steward gushing after "I'll
bring the van Saturday" — reads as a bot with a keyword list, and does more
damage to trust than silence ever does. The prompt is written to refuse, and
everything ambiguous is a refusal.

**Once per item, ever.** The invitation is posted under a deterministic id, so a
second heartfelt message on the same thread finds the invitation already there
and says nothing. Being asked twice is what would make it read as a script.
"""

import json
import logging
from typing import NamedTuple, Optional

from google.genai import types

from classify import model_name, vertex_client
from firebase_app import get_db
from messages import agent_message_id, get_agent_user, post_message
from models import Item, Message

logger = logging.getLogger(__name__)

BEHAVIOR = "memory"

PROMPT = """A family is sorting out the belongings of someone who has died. They are talking
in a shared thread about one object.

The object: {category}{era}

Someone has just written:
  \"\"\"{text}\"\"\"

Decide one thing: is this a **personal memory or story about this object** —
something that happened, someone who used it, a moment it was part of?

Say yes only for a genuine recollection. Say no to everything else, including:
  - logistics, arrangements, dates, offers to help, "I'll collect it Saturday"
  - opinions about what should happen to it, or what it is worth
  - saying they want it, or that it matters to them, without a story
  - a description of the object, however fond
  - questions, thanks, agreement, a joke

Be strict. If you are unsure, say no. Prompting a family for memories after
somebody wrote about a van hire would be worse than staying quiet.

If it *is* a memory, also write the single sentence Steward should say next.
It should:
  - acknowledge what {name} actually said, in a few words — not "what a lovely
    memory" alone, but something showing it was read
  - invite the others to share one of their own, once, without pressure
  - be warm and plain. No exclamation marks. No "treasure", "priceless",
    "heartwarming". Two sentences at most.

Good: "The sound of it on Sunday mornings is exactly the kind of thing that
gets lost. Does anyone else remember the clock?"
Bad: "What a beautiful and heartwarming memory! We would LOVE to hear more!"

Reply with JSON only:
{{"is_memory": true, "invitation": "one or two sentences"}}"""


class MemoryVerdict(NamedTuple):
    is_memory: bool
    invitation: Optional[str] = None
    # Set when the model could not be reached or understood. Distinct from a
    # confident "no" so a caller can tell silence-by-judgement from
    # silence-by-failure.
    failed: bool = False


def _response_schema() -> types.Schema:
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "is_memory": types.Schema(type=types.Type.BOOLEAN),
            "invitation": types.Schema(type=types.Type.STRING),
        },
        required=["is_memory"],
    )


def already_invited(item_id: str) -> bool:
    """Has Steward already asked, on this item?"""
    return (
        get_db()
        .collection(Message.COLLECTION)
        .document(agent_message_id(BEHAVIOR, item_id))
        .get()
        .exists
    )


def read_message(item: Item, name: str, text: str) -> MemoryVerdict:
    """Ask whether this is a memory, and if so what to say. Never raises.

    One call for both, like `marketplace.recommend_channel` — the judgement and
    the sentence depend on each other, and a second call would be free to write
    a warm reply to something the first call had already decided was a van
    booking.
    """
    era = f" ({item.ai_est_era_or_brand})" if item.ai_est_era_or_brand else ""
    try:
        response = vertex_client().models.generate_content(
            model=model_name(),
            contents=PROMPT.format(
                category=item.ai_category, era=era, name=name, text=text.strip()
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_response_schema(),
            ),
        )
        raw = (response.text or "").strip()
    except Exception:  # noqa: BLE001 — a failed read is a silent one
        logger.exception("memory check failed for item %s", item.id)
        return MemoryVerdict(False, failed=True)

    try:
        payload, _ = json.JSONDecoder().raw_decode(raw)
    except Exception:  # noqa: BLE001
        logger.warning("memory check returned non-JSON for item %s", item.id)
        return MemoryVerdict(False, failed=True)

    if not payload.get("is_memory"):
        return MemoryVerdict(False)

    invitation = str(payload.get("invitation") or "").strip()
    # A yes with nothing to say is not a yes. Silence beats a blank prompt.
    if not invitation:
        return MemoryVerdict(False)
    return MemoryVerdict(True, invitation)


def maybe_invite_memories(
    item: Item, author_name: str, text: str
) -> Optional[Message]:
    """Consider inviting the family to share a memory. Returns the post, or None.

    Never raises, and never blocks: the person's message is already in the feed
    by the time this runs, and losing it over a model call would be indefensible.

    Checked before the model call, not after — if Steward has already asked on
    this item there is nothing to decide, and paying Gemini to tell us so would
    be waste on every subsequent message in the thread.
    """
    try:
        if already_invited(item.id):
            return None

        verdict = read_message(item, author_name, text)
        if not verdict.is_memory or not verdict.invitation:
            return None

        return post_message(
            estate_id=item.estate_id,
            user_id=get_agent_user().id,
            text=verdict.invitation,
            item_id=item.id,
            message_id=agent_message_id(BEHAVIOR, item.id),
        )
    except Exception as exc:  # noqa: BLE001 — a courtesy, never a gate
        logger.warning("could not consider a memory invitation on %s: %s", item.id, exc)
        return None
