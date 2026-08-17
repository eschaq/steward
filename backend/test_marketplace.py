"""End-to-end check of the Tier 2 listing draft, against real Firestore and a
real Gemini call.

Not a test suite — a script. Four cases:

  (a) A resolved item routed to sell gets a MarketplaceListing with a real
      platform, a reason and a description that are about *that item*, a usable
      asking price, and a title that isn't shouting.
  (b) A second item in a different category gets a different, equally specific
      recommendation — the check that this is not boilerplate with a name
      swapped in.
  (c) A donate disposition is refused, not silently skipped.
  (d) An item with no disposition at all is refused.

Idempotent: deterministic ids throughout, and prior listings are cleared first.

Usage:
    .venv/bin/python test_marketplace.py

Exit codes: 0 all four behaved, 1 a real logic failure, 2 Gemini refused the
call so recommendation quality could not be judged.
"""

import sys
from datetime import datetime, timezone

from dispositions import get_disposition, record_disposition_decision
from firebase_app import PROJECT_ID, get_db
from items import get_item
from marketplace import (
    RECOMMENDATION_FAILED_REASON,
    MarketplaceError,
    get_listing,
    listing_id,
    recommend_channel,
)
from membership import accept_invite, create_auth_user, invite_to_estate
from models import (
    Item,
    ItemStatus,
    ListingStatus,
    MarketplaceListing,
    MembershipRole,
    Platform,
    Resolution,
    ResolutionType,
    SuggestedDisposition,
)
from resolutions import get_resolution, resolve_item
from test_claims import BENEFICIARIES, ESTATE_ID
from test_dispositions import clear_decision
from test_resolutions import EXECUTOR, clear_resolution


from test_guard import require_destructive_ok

require_destructive_ok(__name__, "test_marketplace.py", "the test-marketplace-* items it owns")

# Fixtures this suite creates and owns outright.
#
# These used to be demo-brass-lamp, demo-canteen-cutlery, demo-dinner-service
# and demo-hall-rug — real inventory a walkthrough shows. Every run cleared
# their listings and dispositions and re-decided them, so running the suite
# silently rewrote four items someone might be about to demo. Nothing here
# touches `demo-*` any more.
#
# Two sell items in genuinely different categories, because a boilerplate answer
# would show up as two near-identical reasons. The condition notes are
# deliberately rich: the suite asserts each recommendation draws at least two
# distinctive words from the item's own record, which needs a record with
# distinctive words in it.
SELL_ITEMS = ["test-marketplace-lamp", "test-marketplace-cutlery"]
DONATE_ITEM = "test-marketplace-dinnerware"
NO_DISPOSITION_ITEM = "test-marketplace-undecided"

FIXTURES = {
    "test-marketplace-lamp": (
        "table lamp",
        "Brass column lamp with a pleated shade. Rewired at some point — the "
        "flex is modern and correctly earthed. Shade is water-stained along one "
        "side and slightly out of round.",
        "brass, 1970s",
    ),
    "test-marketplace-cutlery": (
        "silverware",
        "Canteen of cutlery in a baize-lined oak box, service for six. Plating "
        "has worn to the copper on the spoon backs. Two teaspoons are missing "
        "and the box lock does not catch.",
        "Sheffield plate, unmarked",
    ),
    "test-marketplace-dinnerware": (
        "dinnerware",
        "Twelve-place dinner service, transfer-printed in blue. Two side plates "
        "are chipped at the rim and the gravy boat is missing its stand.",
        "Wedgwood, Etruria mark, c. 1930",
    ),
    "test-marketplace-undecided": (
        "rug",
        "Wool hall runner, worn through to the backing in one patch near the door.",
        None,
    ),
}


def make_fixture(item_id: str, executor_uid: str) -> None:
    """Create the item this suite owns, resolved and ready for a disposition.

    Written directly rather than driven through claim → resolve, because what is
    under test is the marketplace recommendation, not the claim flow — and a
    fixture that depends on three other subsystems fails for three reasons that
    have nothing to do with it.
    """
    category, notes, era = FIXTURES[item_id]
    db = get_db()
    db.collection(Item.COLLECTION).document(item_id).set(
        {
            "id": item_id,
            "estate_id": ESTATE_ID,
            "photo_urls": [],
            "ai_category": category,
            "ai_condition_notes": notes,
            "ai_est_era_or_brand": era,
            "ai_classification_confidence": 0.95,
            "suggested_disposition": SuggestedDisposition.UNCERTAIN.value,
            "status": ItemStatus.RESOLVED.value,
            "created_at": datetime.now(timezone.utc),
        }
    )
    db.collection(Resolution.COLLECTION).document(f"resolution__{item_id}").set(
        {
            "id": f"resolution__{item_id}",
            "item_id": item_id,
            "resolved_by_user_id": executor_uid,
            "resolution_type": ResolutionType.EXECUTOR_OVERRIDE.value,
            "resolved_to_user_id": None,
            "notes": "Fixture: resolved so a disposition can be recorded.",
            "resolved_at": datetime.now(timezone.utc),
        }
    )

# Words that mean the model wrote marketing copy rather than talking to a family.
HUSTLE = ["maximis", "maximiz", "best price", "top dollar", "act fast", "don't miss",
          "buyers are waiting", "hot item", "in demand", "quick sale"]

# The same, for listing copy — where the hustle sounds like an auction site.
LISTING_HUSTLE = HUSTLE + ["must see", "must-see", "rare find", "l@@k", "grab a bargain",
                           "won't last", "wont last", "hurry", "steal", "!!"]

failures: list[str] = []


def check(label: str, actual, expected) -> None:
    def show(v):
        return v.value if hasattr(v, "value") else v

    if actual == expected:
        print(f"  ok       {label}: {show(actual)}")
    else:
        failures.append(f"{label}: got {show(actual)!r}, expected {show(expected)!r}")
        print(f"  FAIL     {label}: got {show(actual)!r}, expected {show(expected)!r}")


def clear_listing(item_id: str) -> None:
    get_db().collection(MarketplaceListing.COLLECTION).document(
        listing_id(f"disposition__{item_id}")
    ).delete()


def main() -> int:
    print(f"Project: {PROJECT_ID}")
    print(f"Estate:  {ESTATE_ID}\n")

    print("setup")
    executor_uid = create_auth_user(*EXECUTOR)
    invite_to_estate(ESTATE_ID, EXECUTOR[0], MembershipRole.EXECUTOR)
    accept_invite(ESTATE_ID, executor_uid)

    beneficiary_email, beneficiary_name = BENEFICIARIES[0]
    beneficiary_uid = create_auth_user(beneficiary_email, beneficiary_name)
    invite_to_estate(ESTATE_ID, beneficiary_email, MembershipRole.BENEFICIARY)
    accept_invite(ESTATE_ID, beneficiary_uid)

    # Own fixtures, made fresh each run — no dependence on what a re-seed or a
    # live walkthrough happens to have left behind.
    for item_id in SELL_ITEMS + [DONATE_ITEM, NO_DISPOSITION_ITEM]:
        clear_listing(item_id)
        clear_decision(item_id)
        make_fixture(item_id, executor_uid)
        item = get_item(item_id)
        print(f"  {item_id:28} {item.ai_category:14} {item.status.value}")
    print()

    # --- (a) and (b) two sell items, two recommendations -------------------
    seen: list[tuple[str, str, str]] = []
    for item_id in SELL_ITEMS:
        item = get_item(item_id)
        record_disposition_decision(item_id, SuggestedDisposition.SELL, executor_uid)
        disposition = get_disposition(item_id)
        check(f"{item_id} routes to", disposition.channel, disposition.channel.__class__.SELL_MARKETPLACE)

        listing = recommend_channel(item_id)
        print(f"\n{item_id} — {item.ai_category}")
        print(f"  platform : {listing.platform.value}")
        print(f"  reason   : {listing.platform_recommendation_reason}")

        if listing.platform_recommendation_reason == RECOMMENDATION_FAILED_REASON:
            print("\nBLOCKED — Gemini refused the call, so recommendation quality")
            print("could not be judged. The failure path behaved correctly: the")
            print("listing says plainly that it doesn't know rather than guessing.")
            return 2

        stored = get_listing(disposition.id)
        check("  read back from Firestore", stored is not None, True)
        check("  listing_status", stored.listing_status, ListingStatus.DRAFT)
        check("  disposition_id", stored.disposition_id, disposition.id)
        check("  platform is a real choice", stored.platform in list(Platform), True)
        # The one call fills all four. listing_url stays null — posting it
        # somewhere is a human act, not a generated one.
        check("  a usable asking price", isinstance(stored.suggested_price, float), True)
        check(
            f"  and a sane one (${stored.suggested_price})",
            stored.suggested_price is not None and 0 <= stored.suggested_price <= 100_000,
            True,
        )
        check("  a draft title", bool(stored.listing_draft_title), True)
        check(
            f"  short enough for a title field ({len(stored.listing_draft_title or '')} chars)",
            len(stored.listing_draft_title or "") <= 90,
            True,
        )
        check("  a draft description", bool(stored.listing_draft_description), True)
        check("  listing_url left null", stored.listing_url, None)

        print(f"  price    : {stored.suggested_price}")
        print(f"  title    : {stored.listing_draft_title}")
        print(f"  body     : {stored.listing_draft_description}")

        copy = f"{stored.listing_draft_title} {stored.listing_draft_description}".lower()
        check(
            "  listing copy isn't a sales pitch",
            [word for word in LISTING_HUSTLE if word in copy],
            [],
        )
        # SHOUTED words are the other tell, and one the word list misses.
        shouted = [
            word
            for word in (stored.listing_draft_title or "").split()
            if len(word) > 2 and word.isupper()
        ]
        check("  and isn't shouting", shouted, [])
        # Honest about wear: the description should carry the condition, not
        # quietly drop it. Checked the same way the reason is — overlap with the
        # item's own distinctive words, not a demanded phrase.
        notes = {
            w.strip(".,;:—()'\"").lower()
            for w in item.ai_condition_notes.split()
            if len(w) >= 5
        }
        carried = sorted(w for w in notes if w and w in (stored.listing_draft_description or "").lower())
        check(
            f"  says what's wrong with it ({', '.join(carried[:6]) or 'nothing'})",
            len(carried) >= 2,
            True,
        )

        reason = stored.platform_recommendation_reason
        check("  reason is a real sentence", 25 < len(reason) < 400, True)
        hustle = [word for word in HUSTLE if word in reason.lower()]
        check("  no reseller-hustle language", hustle, [])
        seen.append((item_id, item.ai_category, reason))

    # Boilerplate would look like the same sentence twice.
    print("\nspecific, not boilerplate")
    first, second = seen[0][2], seen[1][2]
    check("  the two reasons differ", first != second, True)
    overlap = len(set(first.lower().split()) & set(second.lower().split()))
    check(f"  and differ in substance (shared words: {overlap})", overlap < 14, True)
    # Specificity means "drawn from this item's own record", not "echoes the
    # category noun". The first version of this check demanded the literal word
    # `silverware` and failed a reason that said "Sheffield plate cutlery set in
    # its oak box" — which is more specific, not less. Overlap with the item's
    # own distinctive words is the thing actually worth asserting.
    for item_id, _, reason in seen:
        item = get_item(item_id)
        source = " ".join(
            [item.ai_category, item.ai_est_era_or_brand or "", item.ai_condition_notes]
        )
        distinctive = {w.strip(".,;:—()'\"").lower() for w in source.split() if len(w) >= 5}
        used = sorted(
            w for w in distinctive if w and w in reason.lower()
        )
        check(
            f"  {item_id} draws on its own record ({', '.join(used) or 'nothing'})",
            len(used) >= 2,
            True,
        )

    # --- (c) a donate disposition is refused --------------------------------
    print("\n(c) donate disposition")
    record_disposition_decision(DONATE_ITEM, SuggestedDisposition.DONATE, executor_uid)
    try:
        recommend_channel(DONATE_ITEM)
        failures.append("a donate disposition was given a marketplace listing")
        print("  FAIL     donate disposition accepted")
    except MarketplaceError as exc:
        print(f"  ok       refused: {exc}")
    check("  nothing written", get_listing(f"disposition__{DONATE_ITEM}"), None)

    # --- (d) no disposition at all ------------------------------------------
    print("\n(d) no disposition yet")
    try:
        recommend_channel(NO_DISPOSITION_ITEM)
        failures.append("an item with no disposition was given a listing")
        print("  FAIL     accepted an item with no disposition")
    except MarketplaceError as exc:
        print(f"  ok       refused: {exc}")
    check("  nothing written", get_listing(f"disposition__{NO_DISPOSITION_ITEM}"), None)

    print()
    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("OK — real platform choices, honest listing copy and a sane price; "
          "donate and undecided both refused.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
