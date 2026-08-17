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

import logging
import os
from collections import Counter, defaultdict

from firebase_admin import auth
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from google.cloud.firestore_v1.base_query import FieldFilter

from agent import AgentError, run_behavior_for_item
from firebase_app import get_db
from mailer import SendResult, send_invite_email
from auth_deps import CallerUid
from claims import ClaimError, get_claims_for_item, record_claim, withdraw_claim
from clarify import ClarificationError, respond_to_clarification
from dispositions import (
    DispositionError,
    advance_disposition,
    disposition_id,
    get_disposition,
    record_disposition_decision,
)
from marketplace import MarketplaceError, get_listing, listing_id, recommend_channel
from classify import classify_bytes
from items import (
    ItemError,
    add_photo_url,
    create_item_from_classification,
    get_item,
    list_items_for_estate,
    remove_item,
    reserve_item_id,
)
from messages import (
    AGENT_USER_ID,
    display_names_for,
    get_messages_for_estate,
    get_messages_for_item,
    post_message,
)
from overrides import get_override_history
from photo_quality import inspect as inspect_photo, should_offer_retake
from photos import MAX_BYTES, PhotoError, store_item_photo
from membership import (
    MembershipError,
    get_membership,
    MembershipRole,
    accept_invite,
    create_auth_user,
    create_estate,
    estates_for_user,
    invite_to_estate,
    list_memberships,
    require_role,
)
from models import (
    Claim,
    Disposition,
    Estate,
    Item,
    MarketplaceListing,
    Message,
    Resolution,
    ResolutionType,
    SuggestedDisposition,
    User,
)
from resolutions import ResolutionError, get_resolution, resolve_item

logger = logging.getLogger(__name__)

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
    # DELETE arrived with claim withdrawal. Still an explicit list rather than
    # "*": nothing here should ever be reachable by PUT or PATCH, and the
    # browser's preflight is where that gets enforced.
    allow_methods=["GET", "POST", "DELETE"],
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


def _summary(item: Item, decided_channel: Optional[str] = None) -> "ItemSummary":
    """One item's wire shape. Shared so the list and the detail never diverge."""
    return ItemSummary(
        decided_channel=decided_channel,
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
    # Whether the invitation email actually went out, and what to say about it.
    # Both are courtesies reported on top of the membership — an invite that
    # could not be emailed is still an invite.
    invite_email_sent: bool = False
    invite_email_note: Optional[str] = None
    # True only when *this* call is what turned a pending invite into a
    # membership — the one moment someone is genuinely new here. Accepting is
    # idempotent, so a second call comes back False.
    first_accept: bool = False


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
    # The estate's own name, so a screen can say "your mother's house" rather
    # than print a document id at someone. Null if the estate record is missing.
    estate_name: Optional[str] = None
    # True when there is an invite here waiting to be accepted — what the client
    # needs in order to offer acceptance rather than a bare "no role here".
    invite_pending: bool = False


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


class ListingDetail(BaseModel):
    """A marketplace channel recommendation.

    Tier 2. Pricing and draft text are separate, later work — those three fields
    come back null, meaning "not written yet" rather than "not applicable".
    """

    listing_id: str
    disposition_id: str
    platform: str
    platform_recommendation_reason: str
    suggested_price: Optional[float] = None
    listing_draft_title: Optional[str] = None
    listing_draft_description: Optional[str] = None
    listing_url: Optional[str] = None
    listing_status: str


class DispositionDetail(BaseModel):
    """Where an item is headed, and — if it is being sold — where it will be
    listed.

    The listing is nested rather than fetched separately: the two are always
    shown together, and a second round trip would only ever be made immediately
    after this one.
    """

    disposition_id: str
    item_id: str
    channel: str
    status: str
    completed_at: Optional[datetime] = None
    listing: Optional[ListingDetail] = None


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
    # Where the executor actually decided it goes, once they have. Distinct from
    # suggested_disposition, which is only ever Steward's reading of the photo.
    # Null means undecided — the ordinary state of most items.
    decided_channel: Optional[str] = None


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
    # And what happened after — where the piece is headed, plus the marketplace
    # channel when it is being sold. Null means nobody has decided yet, which
    # for a settled item is a prompt rather than an absence.
    disposition: Optional[DispositionDetail] = None


class MemberResponse(BaseModel):
    """One person on the estate, as the executor's list needs them."""

    user_id: str
    display_name: str
    email: str
    role: str
    accepted: bool
    invited_at: datetime
    accepted_at: Optional[datetime] = None
    # So the list can say "you" rather than the reader's own name back at them.
    is_you: bool = False


class MemberListResponse(BaseModel):
    estate_id: str
    count: int
    # How many are still waiting — the number the executor is actually watching.
    pending_count: int
    members: list[MemberResponse]


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


# Two paths, one check. Google's frontend intercepts `/healthz` on Cloud Run
# and answers it with its own 404 before the request reaches the container —
# verified: the route is present in the deployed OpenAPI spec, `/healthz/`
# returns the app's own 307 redirect, and `/healthz` returns a GFE error page
# with no `server: Google Frontend` header. `/health` is not reserved, so that
# is the one to probe in production; `/healthz` stays for local and for any
# Kubernetes-shaped deployment, where it is the convention.
@app.get("/health")
@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness check for Cloud Run. The only unauthenticated route."""
    return {"status": "ok"}


# --- membership -------------------------------------------------------------


def _invite_link(email: str) -> Optional[str]:
    """A real Firebase action link for setting a password.

    The same link the "Forgot your password?" control produces, generated here
    so the invitee is told about it rather than having to be told to go looking
    for it. `continueUrl` sends them on to Steward once the password is set,
    when STEWARD_APP_URL names somewhere to send them.

    None on failure — the invite still stands, there is just nothing to email.
    """
    app_url = os.environ.get("STEWARD_APP_URL", "").strip()
    if app_url:
        try:
            return auth.generate_password_reset_link(
                email,
                action_code_settings=auth.ActionCodeSettings(
                    url=app_url, handle_code_in_app=False
                ),
            )
        except Exception:  # noqa: BLE001
            # Most often UNAUTHORIZED_DOMAIN: STEWARD_APP_URL has to be on the
            # project's authorized-domains list. A link that sets a password but
            # doesn't offer a way onward is far better than no link, so fall
            # through rather than give up.
            logger.warning(
                "invite link for %s could not carry a continue URL (%s); "
                "sending a plain one",
                email,
                app_url,
                exc_info=True,
            )
    try:
        return auth.generate_password_reset_link(email)
    except Exception:  # noqa: BLE001 — a courtesy that failed, not a failed invite
        logger.exception("could not generate an invite link for %s", email)
        return None


class CreateEstateRequest(BaseModel):
    name: str


class EstateSummary(BaseModel):
    """One estate this caller belongs to, and what they are there."""

    id: str
    name: str
    role: str
    created_at: datetime


class MyEstatesResponse(BaseModel):
    count: int
    estates: list[EstateSummary]


@app.post("/estates", response_model=EstateSummary, status_code=201)
def post_create_estate(body: CreateEstateRequest, uid: CallerUid) -> EstateSummary:
    """Start a new estate, with you as its executor.

    **Any signed-in caller, no existing role required** — this is the one write
    in the API that cannot be gated on membership, because it is what creates
    the membership. Everything downstream still goes through `require_role`.

    The creator's membership is accepted immediately: there is no invitation to
    accept when you are the person doing the asking.
    """
    try:
        estate = create_estate(body.name, uid)
    except MembershipError as exc:
        raise _conflict(exc) from exc
    return EstateSummary(
        id=estate.id, name=estate.name,
        role=MembershipRole.EXECUTOR.value, created_at=estate.created_at,
    )


@app.get("/me/estates", response_model=MyEstatesResponse)
def get_my_estates(uid: CallerUid) -> MyEstatesResponse:
    """Every estate this caller belongs to, oldest first.

    What the frontend routes on after sign-in, replacing the assumption that
    there is exactly one estate and its id is known at build time. Zero means
    "you have nowhere to go yet"; that is an ordinary state for a new account,
    not an error, so it is an empty list rather than a 404.

    Accepted memberships only — a pending invite is not somewhere you can go.
    """
    pairs = estates_for_user(uid)
    return MyEstatesResponse(
        count=len(pairs),
        estates=[
            EstateSummary(id=e.id, name=e.name, role=r.value, created_at=e.created_at)
            for e, r in pairs
        ],
    )


@app.post("/estates/{estate_id}/invite", response_model=MembershipResponse)
def post_invite(estate_id: str, body: InviteRequest, uid: CallerUid) -> MembershipResponse:
    """Invite someone to an estate, and email them the way in. Executor only.

    The membership is the source of truth; the email is a courtesy on top of it.
    Everything after `invite_to_estate` is best-effort and reported rather than
    raised — a mail server having a bad day must not stop a family from adding
    someone to their own estate.
    """
    try:
        require_role(uid, estate_id, MembershipRole.EXECUTOR)
        if body.create_account:
            create_auth_user(body.email, body.display_name)
        membership = invite_to_estate(estate_id, body.email, body.role)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    link = _invite_link(body.email)
    if link is None:
        result = SendResult(
            False,
            "The invite is recorded, but Steward couldn't produce a sign-in link "
            "for them. Worth telling them yourself.",
        )
    else:
        people = _users_by_id([uid])
        result = send_invite_email(
            to_email=body.email,
            link=link,
            estate_name=_estate_name(estate_id) or "the estate",
            display_name=body.display_name,
            inviter_name=(people.get(uid) or {}).get("display_name"),
        )

    return MembershipResponse(
        estate_id=membership.estate_id,
        user_id=membership.user_id,
        role=membership.role.value,
        accepted=membership.accepted_at is not None,
        invite_email_sent=result.sent,
        invite_email_note=result.note,
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

    `first_accept` says whether this call is the one that flipped the invite.
    Read before the write rather than stored as a flag: EstateMembership's
    fields are fixed by the data model doc, and "have they been welcomed yet"
    is already answerable from `accepted_at` being null. Accepting is
    idempotent, so every later call reports False.
    """
    before = get_membership(estate_id, uid)
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
        first_accept=before is not None and before.accepted_at is None,
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
        estate_name=_estate_name(estate_id),
        invite_pending=bool(membership) and not accepted,
    )


def _users_by_id(user_ids: list[str]) -> dict[str, dict]:
    """The `users` mirror for a set of uids, in one batched read.

    A membership row holds only a uid, and the frontend cannot read `users`, so
    names and emails have to be resolved here.
    """
    if not user_ids:
        return {}
    db = get_db()
    refs = [db.collection(User.COLLECTION).document(uid) for uid in set(user_ids)]
    return {
        snapshot.id: (snapshot.to_dict() or {})
        for snapshot in db.get_all(refs)
        if snapshot.exists
    }


def _estate_name(estate_id: str) -> Optional[str]:
    """The estate's display name, or None if there is no such record.

    One small read, on a call the client already makes once per screen. None
    rather than the id: a screen that has no name to show should say something
    general, not print `seed-estate-001` at a grieving family.
    """
    snapshot = get_db().collection(Estate.COLLECTION).document(estate_id).get()
    if not snapshot.exists:
        return None
    name = (snapshot.to_dict() or {}).get("name")
    return str(name) if name else None


def _as_listing_detail(listing: Optional[MarketplaceListing]) -> Optional[ListingDetail]:
    """MarketplaceListing -> wire shape. The only place that mapping is written."""
    if listing is None:
        return None
    return ListingDetail(
        listing_id=listing.id,
        disposition_id=listing.disposition_id,
        platform=listing.platform.value,
        platform_recommendation_reason=listing.platform_recommendation_reason,
        suggested_price=listing.suggested_price,
        listing_draft_title=listing.listing_draft_title,
        listing_draft_description=listing.listing_draft_description,
        listing_url=listing.listing_url,
        listing_status=listing.listing_status.value,
    )


def _listing_detail(disposition_id: str) -> Optional[ListingDetail]:
    return _as_listing_detail(get_listing(disposition_id))


def _as_disposition_detail(
    disposition: Optional[Disposition], listing: Optional[MarketplaceListing]
) -> Optional[DispositionDetail]:
    """Disposition (+ its listing) -> wire shape, for one item or for a table.

    Shared so the review table and the per-item endpoint can never drift into
    describing the same decision two different ways.
    """
    if disposition is None:
        return None
    return DispositionDetail(
        disposition_id=disposition.id,
        item_id=disposition.item_id,
        channel=disposition.channel.value,
        status=disposition.status.value,
        completed_at=disposition.completed_at,
        listing=_as_listing_detail(listing),
    )


def _dispositions_for_items(item_ids: list[str]) -> dict[str, DispositionDetail]:
    """Every decided item's disposition and listing, keyed by item id.

    Both ids are deterministic — `disposition__{item_id}` and
    `listing__{disposition_id}` — so this is two batched `get_all` reads for the
    whole estate rather than a query per row. Same pattern the resolutions read
    above uses, and the reason this endpoint exists at all.
    """
    if not item_ids:
        return {}
    db = get_db()

    dispositions: dict[str, Disposition] = {}
    refs = [
        db.collection(Disposition.COLLECTION).document(disposition_id(item_id))
        for item_id in item_ids
    ]
    for snapshot in db.get_all(refs):
        if snapshot.exists:
            disposition = Disposition.model_validate(snapshot.to_dict())
            dispositions[disposition.item_id] = disposition

    # Only sell decisions ever have one, so this second read is usually short.
    listings: dict[str, MarketplaceListing] = {}
    listing_refs = [
        db.collection(MarketplaceListing.COLLECTION).document(listing_id(d.id))
        for d in dispositions.values()
    ]
    for snapshot in db.get_all(listing_refs) if listing_refs else []:
        if snapshot.exists:
            listing = MarketplaceListing.model_validate(snapshot.to_dict())
            listings[listing.disposition_id] = listing

    return {
        item_id: detail
        for item_id, disposition in dispositions.items()
        if (detail := _as_disposition_detail(disposition, listings.get(disposition.id)))
    }


@app.get("/items/{item_id}/disposition", response_model=Optional[DispositionDetail])
def get_item_disposition(item_id: str, uid: CallerUid) -> Optional[DispositionDetail]:
    """Where this item is headed, or null if the executor hasn't decided yet.

    Null rather than 404, for the same reason as the resolution endpoint: not
    having been decided is the ordinary state of most items, not a missing
    resource.
    """
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    disposition = get_disposition(item_id)
    if disposition is None:
        return None
    return _as_disposition_detail(disposition, get_listing(disposition.id))


@app.post("/items/{item_id}/disposition/advance", response_model=DispositionDetail)
def post_advance_disposition(item_id: str, uid: CallerUid) -> DispositionDetail:
    """Mark the next thing that actually happened: pending -> in_progress ->
    completed. Executor only.

    A nested path under the disposition rather than a top-level verb, because
    what moves is the Disposition, not the item — the item's status changing to
    `routed` is a consequence. One step per call: the caller says "this
    happened", not "skip to the end".

    403 if the caller is not the executor; 409 if there is no disposition yet or
    it is already completed — the same MembershipError / DispositionError split
    every other write here uses.
    """
    # Load first purely for the 404: advance_disposition would report a missing
    # item as a state conflict, and "no such item" is not a conflict.
    _load_item(item_id)
    try:
        disposition = advance_disposition(item_id, uid)
    except MembershipError as exc:
        raise _forbidden(exc) from exc
    except DispositionError as exc:
        raise _conflict(exc) from exc

    detail = _as_disposition_detail(disposition, get_listing(disposition.id))
    if detail is None:
        raise HTTPException(status_code=500, detail="The disposition vanished mid-update.")
    return detail


@app.post("/items/{item_id}/marketplace-listing", response_model=ListingDetail)
def post_marketplace_listing(item_id: str, uid: CallerUid) -> ListingDetail:
    """Ask where this item should be listed, and record the answer as a draft.

    Executor only, matching the disposition decision it follows from. Refuses an
    item routed anywhere other than a marketplace, and one with no disposition
    at all — see marketplace.py.
    """
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id, MembershipRole.EXECUTOR)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    try:
        recommend_channel(item_id)
    except MarketplaceError as exc:
        raise _conflict(exc) from exc

    disposition = get_disposition(item_id)
    detail = _listing_detail(disposition.id) if disposition else None
    if detail is None:
        # recommend_channel returned without writing, which should be impossible.
        raise HTTPException(
            status_code=500, detail="The recommendation was not saved. Try again?"
        )
    return detail


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


@app.get("/estates/{estate_id}/members", response_model=MemberListResponse)
def get_estate_members(estate_id: str, uid: CallerUid) -> MemberListResponse:
    """Everyone invited to this estate, accepted or still pending.

    Readable by any accepted member, like every other read here: who else is in
    this with you is not privileged information within a family. Inviting is
    still executor-only.

    Names and emails come from the `users` mirror in one batched read — the
    frontend cannot read that collection, and a membership row holds only a uid.
    """
    try:
        require_role(uid, estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    memberships = list_memberships(estate_id)
    people = _users_by_id([m.user_id for m in memberships])

    members = []
    for membership in memberships:
        person = people.get(membership.user_id)
        members.append(
            MemberResponse(
                user_id=membership.user_id,
                # A membership can outlive its user mirror; say so rather than
                # rendering a blank row.
                display_name=(person or {}).get("display_name") or "Someone",
                email=(person or {}).get("email") or "",
                role=membership.role.value,
                accepted=membership.accepted_at is not None,
                invited_at=membership.invited_at,
                accepted_at=membership.accepted_at,
                is_you=membership.user_id == uid,
            )
        )

    return MemberListResponse(
        estate_id=estate_id,
        count=len(members),
        pending_count=sum(1 for m in members if not m.accepted),
        members=members,
    )


class OverrideEntry(BaseModel):
    item_id: str
    item_category: str
    ai_suggested_disposition: str
    executor_chosen_disposition: str
    created_at: datetime
    # Whether Steward had actually formed a view at the time. Every early entry
    # is `uncertain`, which is the honest state of an estate with no history —
    # the UI must not render that as "Steward suggested uncertain".
    steward_had_a_view: bool
    agreed: bool


class CategoryPattern(BaseModel):
    """What this estate has done with one kind of thing, so far.

    The same arithmetic `overrides.suggest_disposition()` runs — deliberately,
    so what the family reads here and what the agent says on an item can never
    tell two different stories.
    """

    category: str
    total: int
    counts: dict[str, int]
    # The leading choice, or null when the estate is genuinely split.
    leaning: Optional[str] = None
    leaning_count: int = 0
    # A dead heat is not a pattern. Named so the UI can say so out loud.
    split: bool = False


class OverrideLogResponse(BaseModel):
    estate_id: str
    count: int
    entries: list[OverrideEntry]
    patterns: list[CategoryPattern]


@app.get("/estates/{estate_id}/override-log", response_model=OverrideLogResponse)
def get_estate_override_log(estate_id: str, uid: CallerUid) -> OverrideLogResponse:
    """What this estate has decided, and the habit the agent reads from it.

    Any accepted member: this is the family's own decision history, the same
    access level as claims and messages. It is also the only place the adaptive
    loop is visible — until now the agent cited a pattern nobody could inspect.

    Returns both the raw entries, oldest first, and the per-category tally the
    suggestion is actually derived from.
    """
    try:
        require_role(uid, estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    entries = sorted(
        get_override_history(estate_id), key=lambda e: e.created_at
    )

    by_category: dict[str, Counter] = defaultdict(Counter)
    for e in entries:
        by_category[e.item_category][e.executor_chosen_disposition.value] += 1

    patterns: list[CategoryPattern] = []
    for category, counts in by_category.items():
        ranked = counts.most_common()
        # Mirrors suggest_disposition(): a tie is reported as a tie rather than
        # resolved into a preference the family never expressed.
        split = len(ranked) > 1 and ranked[0][1] == ranked[1][1]
        patterns.append(
            CategoryPattern(
                category=category,
                total=sum(counts.values()),
                counts=dict(counts),
                leaning=None if split else ranked[0][0],
                leaning_count=0 if split else ranked[0][1],
                split=split,
            )
        )
    # Strongest habit first — that is the one worth reading.
    patterns.sort(key=lambda p: (-p.total, p.category))

    return OverrideLogResponse(
        estate_id=estate_id,
        count=len(entries),
        entries=[
            OverrideEntry(
                item_id=e.item_id,
                item_category=e.item_category,
                ai_suggested_disposition=e.ai_suggested_disposition.value,
                executor_chosen_disposition=e.executor_chosen_disposition.value,
                created_at=e.created_at,
                steward_had_a_view=e.ai_suggested_disposition
                is not SuggestedDisposition.UNCERTAIN,
                agreed=e.ai_suggested_disposition == e.executor_chosen_disposition,
            )
            for e in entries
        ],
        patterns=patterns,
    )


@app.get("/estates/{estate_id}/review", response_model=ReviewResponse)
def get_estate_review(estate_id: str, uid: CallerUid) -> ReviewResponse:
    """Every item with its claim count and its decision, in one request.

    Removed items are absent here for the same reason they are absent from the
    dashboard — `list_items_for_estate` leaves them out, so this inherits the
    filter rather than repeating it.

    The review table needs four things per item and the client would otherwise
    ask for them one item at a time — 38 items became 114 round trips. Reads are
    batched here instead: claims by chunked `in` query, resolutions and
    dispositions (and their listings) by their deterministic document ids.

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

    dispositions = _dispositions_for_items(item_ids)

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
                disposition=dispositions.get(item.id),
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
    # One batched read for the whole inventory, not one per card: the ids are
    # deterministic, so this costs a `get_all` rather than N round trips.
    decided = _dispositions_for_items([item.id for item in items])
    return ItemListResponse(
        estate_id=estate_id,
        count=len(items),
        items=[
            _summary(item, decided[item.id].channel if item.id in decided else None)
            for item in items
        ],
    )


@app.get("/items/{item_id}", response_model=ItemSummary)
def get_one_item(item_id: str, uid: CallerUid) -> ItemSummary:
    """One item. Any accepted member of its estate."""
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc
    # One extra document read so a single item describes itself the same way the
    # list does. The detail screen still fetches the full disposition separately
    # — it needs the listing and the reason, which no summary carries.
    disposition = get_disposition(item_id)
    return _summary(item, disposition.channel.value if disposition else None)


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


class PhotoConcern(BaseModel):
    """Why a photograph looked unusable, and what to say about it."""

    problem: str
    message: str
    brightness: Optional[float] = None
    sharpness: Optional[float] = None
    contrast: Optional[float] = None
    took_ms: Optional[float] = None


def _photo_concern(data: bytes, accept_anyway: bool) -> None:
    """Look at a photograph before spending a Gemini call on it.

    Shared by both upload paths, so the judgement and the wording exist once.

    Raises 422 with the concern attached when the picture looks hopeless and
    the caller has not already said "use it anyway". Nothing is stored and no
    classification runs, so a retake costs the person a moment rather than a
    round trip through the model.

    `accept_anyway` is the whole reason this is a 422 and not a refusal: the
    check is a convenience, and someone who knows their photograph is fine must
    be able to say so and be believed.
    """
    if accept_anyway:
        return
    verdict = inspect_photo(data)
    if not should_offer_retake(verdict):
        return
    raise HTTPException(
        status_code=422,
        detail={
            "kind": "photo_concern",
            **PhotoConcern(
                problem=verdict.problem or "unclear",
                message=verdict.message or "That photo may not be usable.",
                brightness=verdict.brightness,
                sharpness=verdict.sharpness,
                contrast=verdict.contrast,
                took_ms=verdict.took_ms,
            ).model_dump(),
        },
    )


class ClarifyRequest(BaseModel):
    text: str


class ClarifyResponse(BaseModel):
    """What the answer did — enough for the UI to say so without a refetch."""

    item: ItemSummary
    # Whether the re-reading cleared the confidence threshold and the item moved
    # out of needs_clarification.
    cleared: bool
    confidence: float
    previous_category: str
    # True when the re-reading itself failed. Distinct from `cleared: false`,
    # which means the model looked again and still isn't sure.
    failed: bool
    # The two messages this added to the thread, so the client can append rather
    # than refetch the whole feed.
    messages: list[MessageResponse]


@app.post("/items/{item_id}/clarify", response_model=ClarifyResponse)
def post_clarify_item(
    item_id: str, body: ClarifyRequest, uid: CallerUid
) -> ClarifyResponse:
    """Answer the agent's question about an item it couldn't place.

    **Any accepted member**, not just the executor: identifying a belonging is
    exactly the thing a family knows and the executor may not. The gate is
    membership.

    409 if the item isn't waiting on an answer — the agent asks this question
    once, and answering something already identified is a state mistake rather
    than a permission one.
    """
    _load_item(item_id)
    try:
        result = respond_to_clarification(item_id, uid, body.text)
    except MembershipError as exc:
        raise _forbidden(exc) from exc
    except ClarificationError as exc:
        raise _conflict(exc) from exc

    added = [m for m in (result.answer, result.reply) if m is not None]
    return ClarifyResponse(
        item=_summary(result.item),
        cleared=result.cleared,
        confidence=result.confidence,
        previous_category=result.previous_category,
        failed=result.failed,
        messages=_message_responses(added),
    )


class WithdrawResponse(BaseModel):
    item_id: str
    # How many claim documents came off — more than one when the person had
    # claimed twice, which the data model deliberately allows.
    withdrawn: int
    # The item's status afterwards, so the caller doesn't have to refetch to
    # know whether a contested item just settled back down.
    status: str


@app.delete("/items/{item_id}/claim", response_model=WithdrawResponse)
def delete_item_claim(item_id: str, uid: CallerUid) -> WithdrawResponse:
    """Take your own name back off an item.

    **DELETE, and it means it** — unlike `/items/{id}/remove`, the Claim
    documents genuinely go away. There is no withdrawn flag on Claim in the data
    model, and inventing one would be a schema change to record an absence the
    collection can already express by not containing the row.

    **The claimant's own call, not the executor's.** Any accepted member may do
    this, and a caller can only ever withdraw their own claim because the uid
    comes from their verified token and never from the path or the body — the
    "not someone else's" guarantee is structural here, not a check that could be
    forgotten.

    404 if there is no such item, or if this person has no claim on it: asking
    to take back something you never put down is a mistake worth naming rather
    than a silent success.
    """
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    try:
        withdrawn, status = withdraw_claim(item_id, uid)
    except ClaimError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return WithdrawResponse(item_id=item_id, withdrawn=withdrawn, status=status.value)


@app.post("/items/{item_id}/photo", response_model=ItemSummary)
async def post_item_photo(
    item_id: str,
    uid: CallerUid,
    file: UploadFile = File(...),
    accept_anyway: bool = False,
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

    _photo_concern(data, accept_anyway)

    try:
        url = store_item_photo(item_id, data, file.content_type)
    except PhotoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _summary(add_photo_url(item_id, url))


@app.post("/estates/{estate_id}/items", response_model=ItemSummary, status_code=201)
async def post_estate_item(
    estate_id: str,
    uid: CallerUid,
    file: UploadFile = File(...),
    accept_anyway: bool = False,
) -> ItemSummary:
    """Catalogue a new belonging from a photograph. Executor only.

    The entry point of the whole thing: one photograph in, one Item out. Same
    executor gate as the append-photo endpoint, for the same reason —
    cataloguing is the executor's job.

    Nothing here decides anything. The photo goes to Cloud Storage through
    `store_item_photo`, the bytes go to `classify_bytes`, and
    `create_item_from_classification` does the rest exactly as it does for the
    seed script: the confidence threshold picks the status, the OverrideLog
    weights the suggestion, and an item that lands in `needs_clarification` gets
    the agent's clarifying question posted to the family's feed. This function
    adds no judgement of its own, which is why a photo uploaded here behaves
    identically to one classified from disk.

    A classification that fails does **not** fail the request: it comes back as
    confidence 0.0 and the item lands in `needs_clarification` with an honest
    note, which is the whole point of that status.
    """
    try:
        require_role(uid, estate_id, MembershipRole.EXECUTOR)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    data = await file.read()
    if len(data) > MAX_BYTES:
        # 413 rather than 409: this is about the request, not any item's state.
        raise HTTPException(
            status_code=413,
            detail=f"That photo is larger than {MAX_BYTES // 1024 // 1024}MB.",
        )

    # Before anything is stored or classified: is this picture worth the call?
    _photo_concern(data, accept_anyway)

    # The id is reserved first so the photograph can be filed under the item it
    # belongs to, before that item exists.
    item_id = reserve_item_id()
    try:
        url = store_item_photo(item_id, data, file.content_type)
    except PhotoError as exc:
        # Rejected before any Gemini call and before any document is written —
        # an unusable file leaves nothing behind.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    classification = classify_bytes(data, file.content_type or "image/png")
    item = create_item_from_classification(
        estate_id=estate_id,
        classification=classification,
        # Only the stored URL. The seed and test paths also record the local
        # file they read, which is why photo_urls[0] is not always displayable
        # elsewhere; nothing created here has that problem.
        photo_urls=[url],
        item_id=item_id,
    )
    return _summary(item)


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


@app.post("/items/{item_id}/remove", response_model=ItemSummary)
def post_remove_item(item_id: str, uid: CallerUid) -> ItemSummary:
    """Take an item off the list. Executor only.

    **POST, not DELETE.** DELETE would promise that the resource goes away, and
    it does not: the document stays, its claims and messages stay attached, and
    the item stays readable at this same URL. Naming the action honestly beats
    borrowing a verb whose meaning is wrong here — and it matches the other
    action endpoints (`/claim`, `/resolve`, `/disposition`).

    **Idempotent.** Removing something already removed asks for a state it is
    already in, so there is nothing to refuse; the second call returns the same
    item and writes nothing.
    """
    item = _load_item(item_id)
    try:
        require_role(uid, item.estate_id, MembershipRole.EXECUTOR)
    except MembershipError as exc:
        raise _forbidden(exc) from exc

    try:
        return _summary(remove_item(item_id))
    except ItemError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
