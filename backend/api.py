"""The HTTP surface Cloud Run serves.

Every route is thin on purpose. Authentication is `auth_deps.current_uid`;
**authorization is not implemented here** — it stays in `require_role` inside
membership.py and in the state gates inside resolutions.py and dispositions.py,
which are already verified against real Firestore. A route that re-decided those
questions would be a second copy of the rules, free to drift from the first.

So each handler does three things: establish who is calling, hand off to the
function that owns the operation, and translate that function's exceptions into
status codes.

    401  no token, or a token that doesn't verify        (auth_deps)
    403  authenticated, but not allowed                  (MembershipError)
    404  no such item                                    (route-level lookup)
    409  allowed, but the thing isn't in a state for it  (Claim/Resolution/DispositionError)

This is the same mapping the frontend service will rely on; it never touches
Firestore directly (CLAUDE.md's trust boundary).
"""

from typing import Optional

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import AgentError, run_behavior_for_item
from auth_deps import CallerUid
from claims import ClaimError, record_claim
from dispositions import DispositionError, record_disposition_decision
from items import get_item, list_items_for_estate
from membership import (
    MembershipError,
    MembershipRole,
    accept_invite,
    create_auth_user,
    invite_to_estate,
    require_role,
)
from models import Item, ResolutionType, SuggestedDisposition
from resolutions import ResolutionError, resolve_item

app = FastAPI(
    title="Steward",
    description="Estate belongings disposition — backend API.",
)

# The frontend is a separate Cloud Run service, so every browser call is
# cross-origin. An explicit allow-list, not "*": credentials ride on the
# Authorization header, and a wildcard would let any page on the internet make
# authenticated calls on a signed-in user's behalf. Set STEWARD_ALLOWED_ORIGINS
# (comma-separated) to the frontend's URL when it is deployed.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "STEWARD_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


# --- shared plumbing --------------------------------------------------------


def _load_item(item_id: str) -> Item:
    """The item, or a 404.

    Some of the functions below re-read the item themselves. That second read is
    deliberate: it keeps the state gate inside the function that owns it, and
    buys a real 404 here instead of a 409 that means "no such thing".
    """
    item = get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"No item {item_id}.")
    return item


def _forbidden(exc: MembershipError) -> HTTPException:
    return HTTPException(status_code=403, detail=str(exc))


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


# --- request/response bodies ------------------------------------------------


class InviteRequest(BaseModel):
    email: str
    role: MembershipRole = MembershipRole.BENEFICIARY
    # An invitee needs a Firebase Auth account before a membership can point at
    # them; off by default so inviting a stranger is a deliberate act.
    create_account: bool = False
    display_name: Optional[str] = None


class MembershipResponse(BaseModel):
    estate_id: str
    user_id: str
    role: str
    accepted: bool


class ClaimRequest(BaseModel):
    comment: Optional[str] = None


class ClaimResponse(BaseModel):
    claim_id: str
    item_id: str
    user_id: str
    # The item's status after the claim — `claimed`, or `contested` if someone
    # else already asked for it.
    item_status: str


class ResolveRequest(BaseModel):
    resolution_type: ResolutionType
    resolved_to_user_id: Optional[str] = None
    notes: str = ""


class ResolutionResponse(BaseModel):
    resolution_id: str
    item_id: str
    resolution_type: str
    resolved_to_user_id: Optional[str] = None
    item_status: str


class DispositionRequest(BaseModel):
    executor_chosen_disposition: SuggestedDisposition


class DispositionResponse(BaseModel):
    disposition_id: str
    item_id: str
    channel: str
    status: str
    override_log_id: str


class ItemSummary(BaseModel):
    id: str
    estate_id: str
    ai_category: str
    ai_condition_notes: str
    ai_est_era_or_brand: Optional[str] = None
    ai_classification_confidence: float
    suggested_disposition: str
    status: str
    photo_urls: list[str] = Field(default_factory=list)


class ItemListResponse(BaseModel):
    estate_id: str
    count: int
    items: list[ItemSummary]


class AgentMessageResponse(BaseModel):
    behavior: str
    item_id: str
    item_status: str
    status: str
    message_id: Optional[str] = None


# --- health -----------------------------------------------------------------


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness check for Cloud Run. The only unauthenticated route."""
    return {"status": "ok"}


# --- membership -------------------------------------------------------------


@app.post("/estates/{estate_id}/invite", response_model=MembershipResponse)
def post_invite(estate_id: str, body: InviteRequest, uid: CallerUid) -> MembershipResponse:
    """Invite someone to an estate. Executor only."""
    try:
        require_role(uid, estate_id, MembershipRole.EXECUTOR)
        if body.create_account:
            create_auth_user(body.email, body.display_name)
        membership = invite_to_estate(estate_id, body.email, body.role)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    return MembershipResponse(
        estate_id=membership.estate_id,
        user_id=membership.user_id,
        role=membership.role.value,
        accepted=membership.accepted_at is not None,
    )


@app.post("/estates/{estate_id}/accept", response_model=MembershipResponse)
def post_accept(estate_id: str, uid: CallerUid) -> MembershipResponse:
    """Accept your own invite.

    No `require_role` here, and that is the point: a pending invitee has no role
    yet — that's exactly what they're accepting. The caller can only ever accept
    their own invite, because the uid comes from their verified token and not
    from the request body.

    firestore.rules lets only the executor write a membership row, so this
    endpoint is the path an invitee has to take.
    """
    try:
        membership = accept_invite(estate_id, uid)
    except MembershipError as exc:
        # No invite to accept is a 404 about the invite, not a permission problem.
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return MembershipResponse(
        estate_id=membership.estate_id,
        user_id=membership.user_id,
        role=membership.role.value,
        accepted=membership.accepted_at is not None,
    )


# --- items ------------------------------------------------------------------


@app.get("/estates/{estate_id}/items", response_model=ItemListResponse)
def get_estate_items(estate_id: str, uid: CallerUid) -> ItemListResponse:
    """The estate's inventory. Any accepted member."""
    try:
        require_role(uid, estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    items = list_items_for_estate(estate_id)
    return ItemListResponse(
        estate_id=estate_id,
        count=len(items),
        items=[
            ItemSummary(
                id=item.id,
                estate_id=item.estate_id,
                ai_category=item.ai_category,
                ai_condition_notes=item.ai_condition_notes,
                ai_est_era_or_brand=item.ai_est_era_or_brand,
                ai_classification_confidence=item.ai_classification_confidence,
                suggested_disposition=item.suggested_disposition.value,
                status=item.status.value,
                photo_urls=item.photo_urls,
            )
            for item in items
        ],
    )


@app.post("/items/{item_id}/claim", response_model=ClaimResponse)
def post_claim(item_id: str, body: ClaimRequest, uid: CallerUid) -> ClaimResponse:
    """Claim an item. Any accepted member of that item's estate.

    The claimant is the caller — there is no user_id in the body to forge.
    """
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    try:
        claim, item_status = record_claim(item_id, uid, comment=body.comment)
    except ClaimError as exc:
        raise _conflict(exc) from exc

    return ClaimResponse(
        claim_id=claim.id,
        item_id=claim.item_id,
        user_id=claim.user_id,
        item_status=item_status.value,
    )


@app.post("/items/{item_id}/resolve", response_model=ResolutionResponse)
def post_resolve(item_id: str, body: ResolveRequest, uid: CallerUid) -> ResolutionResponse:
    """Resolve a claimed or contested item. Executor only.

    The executor check and the "is it resolvable" check both live in
    resolve_item; this only maps their exceptions.
    """
    _load_item(item_id)
    try:
        resolution = resolve_item(
            item_id,
            resolved_by_user_id=uid,
            resolution_type=body.resolution_type,
            resolved_to_user_id=body.resolved_to_user_id,
            notes=body.notes,
        )
    except MembershipError as exc:
        raise _forbidden(exc) from exc
    except ResolutionError as exc:
        raise _conflict(exc) from exc

    return ResolutionResponse(
        resolution_id=resolution.id,
        item_id=resolution.item_id,
        resolution_type=resolution.resolution_type.value,
        resolved_to_user_id=resolution.resolved_to_user_id,
        item_status=_load_item(item_id).status.value,
    )


@app.post("/items/{item_id}/disposition", response_model=DispositionResponse)
def post_disposition(
    item_id: str, body: DispositionRequest, uid: CallerUid
) -> DispositionResponse:
    """Record where a resolved item is headed. Executor only.

    Writes the Disposition row and the OverrideLog entry in one batch — see
    dispositions.py.
    """
    _load_item(item_id)
    try:
        entry, disposition = record_disposition_decision(
            item_id, body.executor_chosen_disposition, uid
        )
    except MembershipError as exc:
        raise _forbidden(exc) from exc
    except DispositionError as exc:
        raise _conflict(exc) from exc

    return DispositionResponse(
        disposition_id=disposition.id,
        item_id=disposition.item_id,
        channel=disposition.channel.value,
        status=disposition.status.value,
        override_log_id=entry.id,
    )


# --- the agent --------------------------------------------------------------


@app.post("/items/{item_id}/agent-message", response_model=AgentMessageResponse)
async def post_agent_message(item_id: str, uid: CallerUid) -> AgentMessageResponse:
    """Have the agent say its piece about this item.

    Any accepted member of the estate can ask; the agent decides what to say
    based on the item's status. 409 if the item is in a state no behavior
    attaches to. Calling twice is safe — the second call reports that the message
    was already there rather than posting a second one.
    """
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    try:
        result = await run_behavior_for_item(item_id)
    except AgentError as exc:
        raise _conflict(exc) from exc

    return AgentMessageResponse(**result)
