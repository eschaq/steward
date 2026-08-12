"""The HTTP surface Cloud Run will serve — one route, deliberately.

Enough to prove the ADK wiring works end to end and nothing more. No auth
middleware, no other routes; both are later work, and the frontend service will
reach Firestore only through here (CLAUDE.md's trust boundary).

    POST /items/{item_id}/agent-message

Runs whichever agent behavior the item's status calls for: the clarifying
question for `needs_clarification`, the mediating suggestion for `contested`.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent import AgentError, run_behavior_for_item

app = FastAPI(
    title="Steward",
    description="Estate belongings disposition — backend API.",
)


class AgentMessageResponse(BaseModel):
    """What the agent did, in the caller's terms."""

    behavior: str
    item_id: str
    item_status: str
    # "posted", or the behavior's already-said-this value.
    status: str
    message_id: str | None = None


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness check for Cloud Run."""
    return {"status": "ok"}


@app.post("/items/{item_id}/agent-message", response_model=AgentMessageResponse)
async def post_agent_message(item_id: str) -> AgentMessageResponse:
    """Have the agent say its piece about this item.

    404 if the item doesn't exist; 409 if it is in a state no behavior attaches
    to. Calling twice is safe — the second call reports that the message was
    already there rather than posting a second one.
    """
    try:
        result = await run_behavior_for_item(item_id)
    except AgentError as exc:
        status_code = 404 if str(exc).startswith("No item ") else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return AgentMessageResponse(**result)
