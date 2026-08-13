"""Seed the demo estate with a varied, plausible inventory.

**Not a test script.** Nothing in test_*.py depends on these documents, and this
depends on nothing they create. It exists so the dashboard shows an estate that
looks like an estate, instead of the twenty-odd near-identical fixtures the
verification suites leave behind.

Every document written here has a `demo-` id prefix. That prefix is the only
provenance marker available: Item's shape is fixed by
docs/estate-agent-data-model.md and this script does not get to invent a
`source` field. So:

    demo-*   hand-written here. The ai_* values are *plausible*, not produced by
             Gemini. Nothing in this file went near the classifier.
    test-*   fixtures from the backend verification suites.
    anything else — came through the real pipeline (classify.py -> items.py).

Coherence rules this follows, because seed data that contradicts itself is worse
than no seed data:

  * a `claimed` item has one Claim behind it; a `contested` item has two, from
    two different people
  * a `resolved` or `routed` item has a Resolution recorded by the executor
  * `suggested_disposition` stays `uncertain` throughout — see the note at the
    bottom of this file

Idempotent: fixed document ids, and prior demo claims/resolutions are cleared
before the run so re-seeding doesn't stack duplicates.

Usage:
    .venv/bin/python seed_demo_items.py
"""

import sys
from datetime import datetime, timedelta, timezone

from google.cloud.firestore_v1.base_query import FieldFilter

from firebase_app import PROJECT_ID, get_db
from membership import create_auth_user, membership_id
from models import (
    Claim,
    EstateMembership,
    Item,
    ItemStatus,
    MembershipRole,
    Resolution,
    ResolutionType,
    RoleType,
    SuggestedDisposition,
    User,
)

ESTATE_ID = "seed-estate-001"
PREFIX = "demo-"

EXECUTOR_EMAIL = "steward-test-executor@example.com"

# Two family members for the claims to belong to. Firestore User documents only,
# with no Firebase Auth account — they never sign in, they are here so a claim
# points at a person with a name rather than a bare uid. Same pattern as the
# agent user in messages.py.
FAMILY = [
    ("demo-user-sarah", "sarah@thewillowhouse.family", "Sarah"),
    ("demo-user-david", "david@thewillowhouse.family", "David"),
]


def item(
    slug: str,
    category: str,
    notes: str,
    era: str | None,
    confidence: float,
    status: ItemStatus,
    minutes_ago: int,
) -> Item:
    return Item(
        id=f"{PREFIX}{slug}",
        estate_id=ESTATE_ID,
        photo_urls=[],
        ai_category=category,
        ai_condition_notes=notes,
        ai_est_era_or_brand=era,
        ai_classification_confidence=confidence,
        # Left uncertain on purpose — see the note at the bottom of this file.
        suggested_disposition=SuggestedDisposition.UNCERTAIN,
        status=status,
        # Minutes, not days. The dashboard sorts newest first, and the
        # verification fixtures were written to this estate seconds ago — a
        # backdated demo item sorts underneath twenty-four armchairs and is
        # never seen. These timestamps are honest about when they were seeded;
        # they are not a simulated cataloguing history.
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )


# Fourteen belongings. Condition notes are written one at a time, because a
# templated string repeated fourteen times is exactly the problem this script
# exists to fix — and because the notes are what a family actually reads.
ITEMS = [
    item(
        "dinner-service",
        "dinnerware",
        "Service for eight, near complete — one side plate is missing and the "
        "gravy boat has a hairline crack running from the rim. Gilding on the "
        "cup rims has worn away where they were held.",
        "Wedgwood, Etruria mark, c. 1930",
        0.94,
        ItemStatus.RESOLVED,
        22,
    ),
    item(
        "deco-brooch",
        "jewellery",
        "Openwork brooch, white metal set with clear stones. No hallmark "
        "anywhere on the back. One stone in the lower left is a slightly "
        "different colour and sits proud — likely a later replacement.",
        "Art Deco style, unmarked",
        0.71,
        ItemStatus.CONTESTED,
        9,
    ),
    item(
        "wedding-quilt",
        "textiles",
        "Hand-pieced double-wedding-ring quilt, cotton, quilted by hand at "
        "about eight stitches to the inch. Two blocks along the top edge have "
        "faded noticeably paler than the rest. Clean, no smell of damp.",
        "hand-made, 1940s",
        0.88,
        ItemStatus.CLAIMED,
        16,
    ),
    item(
        "harbour-oil",
        "artwork",
        "Small oil on board, harbour scene with two boats. Signed lower right "
        "but the signature is hard to make out — possibly 'M. Ellery'. Frame is "
        "chipped at the bottom corners and the varnish has yellowed.",
        "signed, dated 1962",
        0.44,
        ItemStatus.NEEDS_CLARIFICATION,
        4,
    ),
    item(
        "hand-planes",
        "hand tools",
        "Three bench planes and a spokeshave in a wooden tote. Blades are sharp "
        "and lightly oiled; someone was still using these. Light surface rust "
        "on the tote's hinges only.",
        "Stanley, mid-century",
        0.91,
        ItemStatus.UNCLAIMED,
        27,
    ),
    item(
        "everyman-books",
        "books",
        "Roughly forty volumes, cloth-bound, mostly novels and essays. Spines "
        "are sunned where the shelf met the window. Several have a name in "
        "fountain pen on the flyleaf.",
        "Everyman's Library, 1930s–50s",
        0.83,
        ItemStatus.UNCLAIMED,
        27,
    ),
    item(
        "writing-desk",
        "writing desk",
        "Oak desk with five small drawers and a leather-topped writing surface. "
        "The leather is worn through to the board at the front edge where "
        "forearms rested. All drawers run smoothly. One brass handle is a "
        "mismatched replacement.",
        "Edwardian, oak",
        0.96,
        ItemStatus.CONTESTED,
        11,
    ),
    item(
        "mantel-clock",
        "mantel clock",
        "Bakelite-cased mantel clock, eight-day movement. Winds and runs but "
        "loses about four minutes a day. Case is sound; the chapter ring has "
        "discoloured to a warm ivory.",
        "Smiths Enfield, c. 1955",
        0.89,
        ItemStatus.ROUTED,
        30,
    ),
    item(
        "canteen-cutlery",
        "silverware",
        "Canteen of cutlery in a baize-lined oak box, service for six. Plating "
        "has worn to the copper on the spoon backs. Two teaspoons are missing "
        "and the box lock does not catch.",
        "Sheffield plate, unmarked",
        0.79,
        ItemStatus.CLAIMED,
        19,
    ),
    item(
        "box-photographs",
        "photographs",
        "A biscuit tin of loose black-and-white photographs, perhaps two "
        "hundred. Almost none are captioned. A few have studio stamps from "
        "Leeds and Scarborough on the reverse.",
        None,
        0.38,
        ItemStatus.NEEDS_CLARIFICATION,
        3,
    ),
    item(
        "hall-rug",
        "rug",
        "Hand-knotted wool runner, red ground with a repeating medallion. Pile "
        "is walked flat down the centre and one end fringe has been re-stitched "
        "by hand. Colours are still strong at the edges.",
        "Hamadan, hand-knotted",
        0.66,
        ItemStatus.UNCLAIMED,
        24,
    ),
    item(
        "brass-lamp",
        "table lamp",
        "Brass column lamp with a pleated shade. Rewired at some point — the "
        "flex is modern and correctly earthed. Shade is water-stained along one "
        "side and slightly out of round.",
        "brass, 1970s",
        0.92,
        ItemStatus.RESOLVED,
        20,
    ),
    item(
        "studio-bowl",
        "studio pottery",
        "Stoneware bowl, tenmoku glaze breaking to rust at the rim. There is an "
        "impressed seal on the foot that neither of us could read. Perfect, no "
        "chips or crazing.",
        "unmarked seal, studio piece",
        0.52,
        ItemStatus.NEEDS_CLARIFICATION,
        6,
    ),
    item(
        "damask-linens",
        "table linens",
        "Double damask tablecloth and eight napkins, monogrammed 'EMH' in "
        "whitework. Laundered and folded, with sharp creases from long storage. "
        "Two faint rust spots near one corner.",
        "Irish damask, monogrammed",
        0.74,
        ItemStatus.UNCLAIMED,
        24,
    ),
]

# Who claimed what. Two names on an item is what makes it contested — the status
# is a consequence of these rows, not a label sitting on its own.
CLAIMS = {
    "demo-wedding-quilt": [("demo-user-sarah", "Mum and I pieced the last two blocks together.")],
    "demo-canteen-cutlery": [("demo-user-david", None)],
    "demo-deco-brooch": [
        ("demo-user-sarah", "She wore this to every wedding I can remember."),
        ("demo-user-david", "I'd promised it to Nina for her eighteenth."),
    ],
    "demo-writing-desk": [
        ("demo-user-david", "Dad wrote every letter at this desk."),
        ("demo-user-sarah", "I'd have room for it, and I'd actually use it."),
    ],
}

# Resolved and routed items need a decision behind them, for the same reason.
RESOLUTIONS = {
    "demo-dinner-service": (
        ResolutionType.EXECUTOR_OVERRIDE,
        None,
        "Nobody asked for it. Donating the service rather than splitting it up.",
    ),
    "demo-brass-lamp": (
        ResolutionType.EXECUTOR_OVERRIDE,
        None,
        "Agreed on the phone — it goes with the desk, whoever ends up with that.",
    ),
    "demo-mantel-clock": (
        ResolutionType.EXECUTOR_OVERRIDE,
        None,
        "Taken to the British Heart Foundation shop on the high street.",
    ),
}


def to_firestore(model) -> dict:
    from enum import Enum

    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in model.model_dump().items()
    }


def clear_previous(db) -> int:
    """Drop demo claims and resolutions so a re-run doesn't stack duplicates.

    Items are overwritten in place by fixed id, so they need no cleanup. Claims
    use generated ids, which is exactly why they do.
    """
    removed = 0
    for item_id in list(CLAIMS) + list(RESOLUTIONS):
        for snapshot in (
            db.collection(Claim.COLLECTION)
            .where(filter=FieldFilter("item_id", "==", item_id))
            .get()
        ):
            snapshot.reference.delete()
            removed += 1
        resolution = db.collection(Resolution.COLLECTION).document(f"resolution__{item_id}")
        if resolution.get().exists:
            resolution.delete()
            removed += 1
    return removed


def main() -> int:
    db = get_db()
    now = datetime.now(timezone.utc)

    print(f"Project: {PROJECT_ID}")
    print(f"Estate:  {ESTATE_ID}\n")

    executor_uid = create_auth_user(EXECUTOR_EMAIL, "Test Executor")
    print(f"executor  {executor_uid}")

    for uid, email, name in FAMILY:
        db.collection(User.COLLECTION).document(uid).set(
            {
                "id": uid,
                "email": email,
                "display_name": name,
                "role_type": RoleType.HUMAN.value,
                "created_at": now,
            }
        )
        db.collection(EstateMembership.COLLECTION).document(
            membership_id(ESTATE_ID, uid)
        ).set(
            {
                "id": membership_id(ESTATE_ID, uid),
                "estate_id": ESTATE_ID,
                "user_id": uid,
                "role": MembershipRole.BENEFICIARY.value,
                "invited_at": now,
                "accepted_at": now,
            }
        )
        print(f"family    {name} ({uid})")

    removed = clear_previous(db)
    if removed:
        print(f"cleaned   {removed} claim/resolution document(s) from a previous seed")
    print()

    tally: dict[str, int] = {}
    for record in ITEMS:
        db.collection(Item.COLLECTION).document(record.id).set(to_firestore(record))
        tally[record.status.value] = tally.get(record.status.value, 0) + 1
        era = record.ai_est_era_or_brand or "—"
        print(
            f"  {record.status.value:<20} {record.ai_category:<16} "
            f"{record.ai_classification_confidence:.2f}  {era}"
        )

    print()
    for item_id, claimants in CLAIMS.items():
        for offset, (uid, comment) in enumerate(claimants):
            doc = db.collection(Claim.COLLECTION).document()
            claim = Claim(
                id=doc.id,
                item_id=item_id,
                user_id=uid,
                claimed_at=now - timedelta(minutes=2 + offset),
                comment=comment,
            )
            doc.set(to_firestore(claim))
        who = ", ".join(uid.replace("demo-user-", "") for uid, _ in claimants)
        print(f"  claims    {item_id:<26} {who}")

    print()
    for item_id, (kind, to_user, notes) in RESOLUTIONS.items():
        resolution = Resolution(
            id=f"resolution__{item_id}",
            item_id=item_id,
            resolved_by_user_id=executor_uid,
            resolution_type=kind,
            resolved_to_user_id=to_user,
            notes=notes,
            resolved_at=now - timedelta(minutes=1),
        )
        db.collection(Resolution.COLLECTION).document(resolution.id).set(
            to_firestore(resolution)
        )
        print(f"  resolved  {item_id:<26} {kind.value}")

    print(f"\n{len(ITEMS)} items seeded — " + ", ".join(
        f"{count} {status}" for status, count in sorted(tally.items())
    ))
    print(
        "\nHand-seeded, not agent-classified: every ai_* value above was written "
        "by hand.\nNothing here went through classify.py. The `demo-` id prefix is "
        "how you tell\nthese apart from pipeline items later."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
