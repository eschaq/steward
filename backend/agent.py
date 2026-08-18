"""The Google ADK layer: Steward's two agent behaviors, exposed as ADK tools.

This is a **structural wrap**, not a rewrite. The copy the family reads and the
Message writing both stay in `messages.py`, untouched — these tools look up what
each behavior needs from Firestore and hand off to the existing functions. The
no-double-post guarantee still lives where it always did, in
`messages._post_once`.

Why the tools are invoked directly rather than through a model:

    Both behaviors are triggered by a *state transition* the backend already
    detects — an item landing in `needs_clarification`, or flipping to
    `contested`. There is no decision for a model to make about which one
    applies, and letting one choose would put the family's message content at the
    mercy of a sampling temperature. So `run_behavior_for_item` dispatches on
    status and invokes the ADK tool through ADK's own `run_async` contract:
    argument validation, tool declarations, and result shape all go through the
    framework, and `steward_agent` below is a real `LlmAgent` holding these
    tools, ready for the model-driven paths (a "what should we do with the
    garage?" conversation) that come later.

Classification is deliberately **not** wrapped as a tool — see README.
"""

import os
from functools import lru_cache
from typing import Any, Optional

from claims import claimant_ids_for_item
from firebase_app import get_db
from messages import post_clarifying_question, post_contested_mediation
from models import Item, ItemStatus

# Gemini Flash by default, matching classify.py; Pro is reserved for complex
# final reasoning (CLAUDE.md).
AGENT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

APP_NAME = "steward"


class AgentError(Exception):
    """The item can't be acted on — it doesn't exist, or isn't in a state with a
    behavior attached."""


def _load_item(item_id: str) -> Item:
    snapshot = get_db().collection(Item.COLLECTION).document(item_id).get()
    if not snapshot.exists:
        raise AgentError(f"No item {item_id}.")
    return Item.model_validate(snapshot.to_dict())


# --- The two behaviors, as plain functions ADK can introspect ---------------
#
# Signatures and docstrings are the tool declarations the model sees, so they
# read as instructions rather than as internal notes.


def ask_about_unclear_item(item_id: str) -> dict[str, Any]:
    """Ask the family to help identify an item the agent couldn't place.

    Use when an item is sitting at needs_clarification. Posts one question to the
    estate's message feed, and does nothing if that question was already asked.

    Args:
        item_id: The item to ask about.

    Returns:
        status: "posted" if a question went out, "already_asked" if it was
            already there, and message_id when one exists.
    """
    item = _load_item(item_id)
    message = post_clarifying_question(
        estate_id=item.estate_id,
        item_id=item.id,
        ai_category=item.ai_category,
        ai_condition_notes=item.ai_condition_notes,
    )
    return {
        "status": "posted" if message else "already_asked",
        "item_id": item.id,
        "message_id": message.id if message else None,
    }


def mediate_contested_item(item_id: str) -> dict[str, Any]:
    """Offer the family a way through when two or more people want the same item.

    Use when an item has just become contested. Posts one mediating suggestion to
    the estate's message feed, and does nothing if that suggestion is already
    there.

    Args:
        item_id: The contested item.

    Returns:
        status: "posted" if a suggestion went out, "already_mediated" if it was
            already there, and message_id when one exists.
    """
    item = _load_item(item_id)
    message = post_contested_mediation(
        item.estate_id, item.id, claimant_ids_for_item(item.id)
    )
    return {
        "status": "posted" if message else "already_mediated",
        "item_id": item.id,
        "message_id": message.id if message else None,
    }


# Which behavior belongs to which state. The backend detects the transition; this
# is the mapping, not a judgement call.
#
# Deliberately plain data — status to function — so that *deciding* whether an
# item has a behavior costs nothing. Building the ADK tools is what's expensive,
# and it happens below, only once something is actually going to run.
BEHAVIOR_FOR_STATUS = {
    ItemStatus.NEEDS_CLARIFICATION: ask_about_unclear_item,
    ItemStatus.CONTESTED: mediate_contested_item,
}


@lru_cache(maxsize=1)
def _adk() -> dict[str, Any]:
    """Import ADK and build the agent and its tools, once, on first use.

    **Imported here rather than at module scope, and this is worth the
    indirection.** `google.adk` pulls in `google.genai` behind it and measured
    1.9s of api.py's 3.2s import — on a Cloud Run instance starting from cold,
    several times that. Every request paid for it, including the ones that only
    wanted to list items, because api.py imports this module for two names.

    Nothing about the stack changes: ADK is still what runs the behaviors, and
    `steward_agent` is still a real `LlmAgent` holding real `FunctionTool`s,
    ready for the model-driven paths that come later. The only difference is
    that the framework loads when a behavior first runs rather than when the
    process starts.

    Cached so the second behavior in a process reuses the first one's agent.
    """
    from google.adk.agents import LlmAgent
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools import FunctionTool
    from google.adk.tools.tool_context import ToolContext

    tools = {
        status: FunctionTool(behavior)
        for status, behavior in BEHAVIOR_FOR_STATUS.items()
    }
    agent = LlmAgent(
        model=AGENT_MODEL,
        name="steward",
        description="Helps a family sort out what happens to the belongings in an estate.",
        instruction=(
            "You are Steward, helping a family decide what happens to the belongings "
            "in an estate someone has left behind. Be warm, unhurried, and "
            "plainspoken — a quiet, steady hand at a kitchen table. Never rush "
            "anyone, never use urgency, and never take a side between two people who "
            "want the same thing.\n\n"
            "When an item can't be identified, ask about it with "
            "ask_about_unclear_item. When two or more people have claimed the same "
            "item, offer a way through with mediate_contested_item. Both tools post "
            "to the family's message feed and will not repeat themselves."
        ),
        tools=list(tools.values()),
    )
    return {
        "agent": agent,
        "tools": tools,
        "InvocationContext": InvocationContext,
        "InMemorySessionService": InMemorySessionService,
        "ToolContext": ToolContext,
    }


def steward_agent() -> Any:
    """The `LlmAgent`, built on first ask. A function now rather than a module
    constant, because a constant is what forced ADK to load at import."""
    return _adk()["agent"]


async def invoke_tool(tool: Any, **args: Any) -> dict[str, Any]:
    """Run an ADK tool through ADK, outside a model turn.

    A tool needs a ToolContext, and a ToolContext needs an InvocationContext, so
    this builds the minimum of both. Going through `run_async` rather than
    calling the function keeps ADK's argument validation and result contract in
    the path.
    """
    adk = _adk()
    session_service = adk["InMemorySessionService"]()
    session = await session_service.create_session(app_name=APP_NAME, user_id=APP_NAME)
    context = adk["InvocationContext"](
        session_service=session_service,
        invocation_id=f"{APP_NAME}-{tool.name}",
        agent=adk["agent"],
        session=session,
    )
    return await tool.run_async(args=args, tool_context=adk["ToolContext"](context))


async def run_behavior_for_item(item_id: str) -> dict[str, Any]:
    """Run whichever agent behavior this item's status calls for.

    Raises AgentError if the item doesn't exist or is in a state no behavior
    attaches to — better than a 200 that quietly did nothing. That refusal is
    decided from `BEHAVIOR_FOR_STATUS` alone, so an item with nothing to say
    never loads the framework to be told so.
    """
    item = _load_item(item_id)
    if item.status not in BEHAVIOR_FOR_STATUS:
        attached = ", ".join(sorted(s.value for s in BEHAVIOR_FOR_STATUS))
        raise AgentError(
            f"Item {item_id} is {item.status.value}; the agent only has something "
            f"to say about an item that is {attached}."
        )

    tool = _adk()["tools"][item.status]
    result = await invoke_tool(tool, item_id=item_id)
    # A FunctionTool reports a bad call by returning {"error": ...} rather than
    # raising, so an unchecked result would read as success.
    if isinstance(result, dict) and "error" in result:
        raise AgentError(f"{tool.name} could not run: {result['error']}")

    return {"behavior": tool.name, "item_status": item.status.value, **result}
