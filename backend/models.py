"""Pydantic models for Steward's Tier 1 core entities.

Fields mirror docs/estate-agent-data-model.md exactly. Do not add or remove
fields here without updating that doc first — it is the source of truth.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EstateStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class RoleType(str, Enum):
    HUMAN = "human"
    # Lets Steward's own agent author Messages through the same table humans use.
    AGENT = "agent"


class MembershipRole(str, Enum):
    EXECUTOR = "executor"
    BENEFICIARY = "beneficiary"


class SuggestedDisposition(str, Enum):
    DISCARD = "discard"
    DONATE = "donate"
    SELL = "sell"
    UNCERTAIN = "uncertain"


class ItemStatus(str, Enum):
    UNCLAIMED = "unclaimed"
    CLAIMED = "claimed"
    CONTESTED = "contested"
    RESOLVED = "resolved"
    ROUTED = "routed"
    NEEDS_CLARIFICATION = "needs_clarification"


class Estate(BaseModel):
    COLLECTION: ClassVar[str] = "estates"

    id: str
    name: str
    executor_user_id: str
    status: EstateStatus
    created_at: datetime = Field(default_factory=_utcnow)


class User(BaseModel):
    COLLECTION: ClassVar[str] = "users"

    id: str
    email: str
    display_name: str
    role_type: RoleType
    created_at: datetime = Field(default_factory=_utcnow)


class EstateMembership(BaseModel):
    COLLECTION: ClassVar[str] = "estate_memberships"

    id: str
    estate_id: str
    user_id: str
    role: MembershipRole
    invited_at: datetime = Field(default_factory=_utcnow)
    # Null means the invite is still pending.
    accepted_at: Optional[datetime] = None


class ResolutionType(str, Enum):
    ASSIGNED_TO_CLAIMANT = "assigned_to_claimant"
    ROTATION = "rotation"
    OUTSIDE_APPRAISAL = "outside_appraisal"
    EXECUTOR_OVERRIDE = "executor_override"


class Resolution(BaseModel):
    COLLECTION: ClassVar[str] = "resolutions"

    id: str
    item_id: str
    # Must hold the executor role on the item's estate — enforced in resolutions.py.
    resolved_by_user_id: str
    resolution_type: ResolutionType
    # Set when the item goes to a specific person (assigned/rotation).
    resolved_to_user_id: Optional[str] = None
    notes: str = ""
    resolved_at: datetime = Field(default_factory=_utcnow)


class Message(BaseModel):
    """One entry in the estate's single unified feed.

    Item-specific and general messages live in the same collection — `item_id`
    is null for general estate discussion. Do not split this by scope.
    """

    COLLECTION: ClassVar[str] = "messages"

    id: str
    estate_id: str
    # Null for general estate discussion, set when the message is about an item.
    item_id: Optional[str] = None
    # May be a human or the `agent` role_type user.
    user_id: str
    text: str
    created_at: datetime = Field(default_factory=_utcnow)


class Claim(BaseModel):
    COLLECTION: ClassVar[str] = "claims"

    id: str
    item_id: str
    user_id: str
    claimed_at: datetime = Field(default_factory=_utcnow)
    comment: Optional[str] = None


class Item(BaseModel):
    COLLECTION: ClassVar[str] = "items"

    id: str
    estate_id: str
    photo_urls: list[str] = Field(default_factory=list)
    ai_category: str
    ai_condition_notes: str
    ai_est_era_or_brand: Optional[str] = None
    # Drives the clarifying-question trigger when low.
    ai_classification_confidence: float = Field(ge=0.0, le=1.0)
    suggested_disposition: SuggestedDisposition
    status: ItemStatus
    created_at: datetime = Field(default_factory=_utcnow)
