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

from datetime import datetime
from typing import Optional

import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from google.cloud.firestore_v1.base_query import FieldFilter

from agent import AgentError, run_behavior_for_item
from firebase_app import get_db
from auth_deps import CallerUid
from claims import ClaimError, get_claims_for_item, record_claim
from dispositions import DispositionError, record_disposition_decision
from items import add_photo_url, get_item, list_items_for_estate
from messages import (
    AGENT_USER_ID,
    display_names_for,
    get_messages_for_estate,
    get_messages_for_item,
    post_message,
)
from photos import MAX_BYTES, PhotoError, store_item_photo
from membership import (
    MembershipError,
    get_membership,
    MembershipRole,
    accept_invite,
    create_auth_user,
    invite_to_estate,
    require_role,
)
from models import Claim, Item, Message, Resolution, ResolutionType, SuggestedDisposition
from resolutions import ResolutionError, get_resolution, resolve_item

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


def _summary(item: Item) -> "ItemSummary":
    """One item's wire shape. Shared so the list and the detail never diverge."""
    return ItemSummary(
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


def _message_responses(thread: list[Message]) -> list["MessageResponse"]:
    """Wire shape for a list of messages, names and item labels resolved.

    Shared by the per-item thread and the estate-wide feed: the agent/human
    distinction and the display-name lookup are decided once, in one place.
    Both lookups are batched over the distinct ids rather than per message.
    """
    names = display_names_for([m.user_id for m in thread])
    categories: dict[str, Optional[str]] = {}
    for item_id in dict.fromkeys(m.item_id for m in thread if m.item_id):
        item = get_item(item_id)
        categories[item_id] = item.ai_category if item else None

    return [
        MessageResponse(
            id=m.id,
            item_id=m.item_id,
            user_id=m.user_id,
            author_name=names.get(m.user_id, "someone"),
            is_agent=m.user_id == AGENT_USER_ID,
            item_category=categories.get(m.item_id) if m.item_id else None,
            text=m.text,
            created_at=m.created_at,
        )
        for m in thread
    ]


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


class MeResponse(BaseModel):
    """The caller's standing on one estate.

    The UI needs this to decide what to *offer* — an executor-only action should
    not be shown to a beneficiary and then rejected. Authorization is still
    enforced server-side on every write; this only governs what is on screen.
    """

    estate_id: str
    user_id: str
    # Null when the caller has no membership at all, or has one but has not
    # accepted it — a pending invite grants no role.
    role: Optional[str] = None
    accepted: bool = False


class ResolutionDetail(BaseModel):
    """A resolution already recorded, for showing what was decided."""

    resolution_id: str
    item_id: str
    resolution_type: str
    resolved_by_user_id: str
    resolved_by_name: str
    resolved_to_user_id: Optional[str] = None
    resolved_to_name: Optional[str] = None
    notes: str = ""
    resolved_at: datetime


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


class MessageResponse(BaseModel):
    id: str
    item_id: Optional[str] = None
    user_id: str
    # Resolved server-side: the frontend cannot read `users`.
    author_name: str
    # Lets the UI give Steward its own voice without hardcoding a uid.
    is_agent: bool
    # The item's category when this message is tied to one, so a feed can name
    # what it is talking about instead of showing a document id.
    item_category: Optional[str] = None
    text: str
    created_at: datetime


class ClaimantResponse(BaseModel):
    claim_id: str
    user_id: str
    # Resolved server-side: the frontend cannot read `users`.
    claimant_name: str
    # So the page can say "You" rather than the reader's own display name.
    is_you: bool
    comment: Optional[str] = None
    claimed_at: datetime


class ClaimListResponse(BaseModel):
    item_id: str
    # Documents, duplicates included — the collection has no uniqueness
    # constraint by design.
    count: int
    # How many *different* people. This is what drives the item's status.
    claimant_count: int
    claims: list[ClaimantResponse]


class MessageListResponse(BaseModel):
    # The item, on a per-item thread; null on the estate-wide feed.
    item_id: Optional[str] = None
    estate_id: Optional[str] = None
    count: int
    messages: list[MessageResponse]


class PostMessageRequest(BaseModel):
    text: str
    # Omitted for general estate discussion; set to tie the message to an item.
    # Nullable by design — see the Message entity in the data model doc.
    item_id: Optional[str] = None


class ReviewRow(BaseModel):
    """One item as the executor's review table needs it.

    Composed from data that already exists — items, claims, resolutions. No new
    entity, and no new collection: this endpoint only saves the client from
    making two requests per item.
    """

    id: str
    ai_category: str
    ai_est_era_or_brand: Optional[str] = None
    ai_classification_confidence: float
    suggested_disposition: str
    status: str
    # Distinct people, which is what drives the status.
    claimant_count: int
    # First photograph, if any — the table shows a thumbnail, and fetching it
    # per row would undo the point of composing this response.
    photo_url: Optional[str] = None
    # Present only when exactly one person asked — that is the case the table
    # can settle in a single click without hiding anything.
    sole_claimant_id: Optional[str] = None
    sole_claimant_name: Optional[str] = None
    # What was decided, when something was.
    decided_type: Optional[str] = None
    decided_to_name: Optional[str] = None
    decided_notes: Optional[str] = None


class ReviewResponse(BaseModel):
    estate_id: str
    count: int
    rows: list[ReviewRow]


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


@app.get("/estates/{estate_id}/me", response_model=MeResponse)
def get_my_standing(estate_id: str, uid: CallerUid) -> MeResponse:
    """What the caller is on this estate — for deciding what to show them.

    Deliberately not a 403 for a non-member: "you have no role here" is a fact
    the UI needs in order to say so plainly, not an error. Every write still
    goes through require_role.
    """
    membership = get_membership(estate_id, uid)
    accepted = bool(membership and membership.accepted_at is not None)
    return MeResponse(
        estate_id=estate_id,
        user_id=uid,
        # A pending invite grants no role — same rule get_role() applies.
        role=membership.role.value if (membership and accepted) else None,
        accepted=accepted,
    )


@app.get("/items/{item_id}/resolution", response_model=Optional[ResolutionDetail])
def get_item_resolution(item_id: str, uid: CallerUid) -> Optional[ResolutionDetail]:
    """What was decided about this item, or null if nothing has been.

    Null rather than 404: "no decision yet" is the ordinary state of most items,
    not a missing resource.
    """
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    resolution = get_resolution(item_id)
    if resolution is None:
        return None

    names = display_names_for(
        [resolution.resolved_by_user_id]
        + ([resolution.resolved_to_user_id] if resolution.resolved_to_user_id else [])
    )
    return ResolutionDetail(
        resolution_id=resolution.id,
        item_id=resolution.item_id,
        resolution_type=resolution.resolution_type.value,
        resolved_by_user_id=resolution.resolved_by_user_id,
        resolved_by_name=names.get(resolution.resolved_by_user_id, "someone"),
        resolved_to_user_id=resolution.resolved_to_user_id,
        resolved_to_name=(
            names.get(resolution.resolved_to_user_id) if resolution.resolved_to_user_id else None
        ),
        notes=resolution.notes,
        resolved_at=resolution.resolved_at,
    )


@app.get("/estates/{estate_id}/review", response_model=ReviewResponse)
def get_estate_review(estate_id: str, uid: CallerUid) -> ReviewResponse:
    """Every item with its claim count and its decision, in one request.

    The review table needs three things per item and the client would otherwise
    ask for them one item at a time — 38 items became 76 round trips. Reads are
    batched here instead: claims by chunked `in` query, resolutions by their
    deterministic document ids.

    Readable by any accepted member, like every other read in this API. The
    *screen* is executor-only, and the resolve action it offers is enforced
    executor-only server-side; nothing here is privileged.
    """
    try:
        require_role(uid, estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    items = list_items_for_estate(estate_id)
    item_ids = [item.id for item in items]
    db = get_db()

    # Claims carry no estate_id, so they are fetched by item. Firestore's `in`
    # takes 30 values at a time.
    claimants: dict[str, list[str]] = {item_id: [] for item_id in item_ids}
    for start in range(0, len(item_ids), 30):
        chunk = item_ids[start : start + 30]
        for snapshot in (
            db.collection(Claim.COLLECTION)
            .where(filter=FieldFilter("item_id", "in", chunk))
            .get()
        ):
            claim = Claim.model_validate(snapshot.to_dict())
            if claim.user_id not in claimants[claim.item_id]:
                claimants[claim.item_id].append(claim.user_id)

    # Resolution ids are deterministic, so these are direct document reads.
    resolutions: dict[str, Resolution] = {}
    refs = [
        db.collection(Resolution.COLLECTION).document(f"resolution__{item_id}")
        for item_id in item_ids
    ]
    for snapshot in db.get_all(refs) if refs else []:
        if snapshot.exists:
            resolution = Resolution.model_validate(snapshot.to_dict())
            resolutions[resolution.item_id] = resolution

    names = display_names_for(
        [uid for ids in claimants.values() for uid in ids]
        + [r.resolved_to_user_id for r in resolutions.values() if r.resolved_to_user_id]
    )

    rows = []
    for item in items:
        who = claimants.get(item.id, [])
        decided = resolutions.get(item.id)
        rows.append(
            ReviewRow(
                id=item.id,
                ai_category=item.ai_category,
                ai_est_era_or_brand=item.ai_est_era_or_brand,
                ai_classification_confidence=item.ai_classification_confidence,
                suggested_disposition=item.suggested_disposition.value,
                status=item.status.value,
                claimant_count=len(who),
                # First *loadable* url — classification records the local file
                # it read, so photo_urls[0] is not necessarily displayable.
                photo_url=next(
                    (u for u in item.photo_urls if u.lower().startswith(("http://", "https://"))),
                    None,
                ),
                sole_claimant_id=who[0] if len(who) == 1 else None,
                sole_claimant_name=names.get(who[0]) if len(who) == 1 else None,
                decided_type=decided.resolution_type.value if decided else None,
                decided_to_name=(
                    names.get(decided.resolved_to_user_id)
                    if decided and decided.resolved_to_user_id
                    else None
                ),
                decided_notes=decided.notes if decided else None,
            )
        )

    return ReviewResponse(estate_id=estate_id, count=len(rows), rows=rows)


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
        items=[_summary(item) for item in items],
    )


@app.get("/items/{item_id}", response_model=ItemSummary)
def get_one_item(item_id: str, uid: CallerUid) -> ItemSummary:
    """One item. Any accepted member of its estate."""
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc
    return _summary(item)


@app.get("/items/{item_id}/messages", response_model=MessageListResponse)
def get_item_messages(item_id: str, uid: CallerUid) -> MessageListResponse:
    """The message thread for one item, oldest first.

    Item-specific slice of the single unified feed — the data model keeps
    general estate discussion in the same collection with a null item_id.
    """
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    thread = get_messages_for_item(item_id)
    return MessageListResponse(
        item_id=item_id,
        estate_id=item.estate_id,
        count=len(thread),
        messages=_message_responses(thread),
    )


@app.get("/items/{item_id}/claims", response_model=ClaimListResponse)
def get_item_claims(item_id: str, uid: CallerUid) -> ClaimListResponse:
    """Who has asked for this item, oldest first, with what they said.

    Visible to any accepted member: a family cannot talk through a contested
    piece if only the executor can see who wants it.
    """
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    claims = get_claims_for_item(item_id)
    names = display_names_for([c.user_id for c in claims])
    return ClaimListResponse(
        item_id=item_id,
        count=len(claims),
        claimant_count=len({c.user_id for c in claims}),
        claims=[
            ClaimantResponse(
                claim_id=c.id,
                user_id=c.user_id,
                claimant_name=names.get(c.user_id, "someone"),
                is_you=c.user_id == uid,
                comment=c.comment,
                claimed_at=c.claimed_at,
            )
            for c in claims
        ],
    )


@app.get("/estates/{estate_id}/messages", response_model=MessageListResponse)
def get_estate_messages(estate_id: str, uid: CallerUid) -> MessageListResponse:
    """The estate's whole feed, oldest first.

    One feed, not two: per the data model, item-specific and general discussion
    live in the same collection and `item_id` is nullable. This returns both,
    interleaved by time — splitting them here would rebuild the separation the
    data model deliberately avoids.
    """
    try:
        require_role(uid, estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    feed = get_messages_for_estate(estate_id)
    return MessageListResponse(
        estate_id=estate_id,
        count=len(feed),
        messages=_message_responses(feed),
    )


@app.post("/estates/{estate_id}/messages", response_model=MessageResponse)
def post_estate_message(
    estate_id: str, body: PostMessageRequest, uid: CallerUid
) -> MessageResponse:
    """Post to the estate's feed. Any accepted member.

    The author is the caller — there is no user_id in the body, so nobody can
    post as somebody else, and nobody can post as Steward.
    """
    try:
        require_role(uid, estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="A message needs something in it.")

    # An item_id is only meaningful for an item in *this* estate. Without this
    # check a member could hang a message off an item they cannot otherwise see.
    if body.item_id:
        item = _load_item(body.item_id)
        if item.estate_id != estate_id:
            raise HTTPException(
                status_code=404,
                detail=f"No item {body.item_id} in estate {estate_id}.",
            )

    message = post_message(
        estate_id=estate_id, user_id=uid, text=text, item_id=body.item_id
    )
    return _message_responses([message])[0]


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


@app.post("/items/{item_id}/photo", response_model=ItemSummary)
async def post_item_photo(
    item_id: str, uid: CallerUid, file: UploadFile = File(...)
) -> ItemSummary:
    """Attach a photograph to an item. Executor only.

    Cataloguing is the executor's job — a beneficiary adding photographs to
    someone else's belongings is a different feature with different questions
    behind it, so this matches the resolve/disposition gate rather than the
    claim one.
    """
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id, MembershipRole.EXECUTOR)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    data = await file.read()
    if len(data) > MAX_BYTES:
        # 413 rather than 409: this is about the request, not the item's state.
        raise HTTPException(
            status_code=413,
            detail=f"That photo is larger than {MAX_BYTES // 1024 // 1024}MB.",
        )

    try:
        url = store_item_photo(item_id, data, file.content_type)
    except PhotoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _summary(add_photo_url(item_id, url))


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
