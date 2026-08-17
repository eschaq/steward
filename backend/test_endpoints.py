"""End-to-end check of the authenticated API against real Firestore.

Not a test suite — a script. It drives the app with FastAPI's TestClient (no
live server) using **real Firebase ID tokens**, minted by signing test users in
against Identity Toolkit. The Admin SDK verifies them exactly as it would in
production; nothing about auth is stubbed.

Every endpoint is exercised three ways:

  * a valid actor            -> 2xx, and the write really happened
  * an unauthorized actor    -> 403, **and nothing was written**
  * no token / a bad token   -> 401

The "nothing was written" half is the point. A 403 that had already written its
document would pass a status-code-only test and still be a hole.

Usage:
    .venv/bin/python test_endpoints.py
"""

import sys

from fastapi.testclient import TestClient

from api import app
from claims import get_claims_for_item
from dev_tokens import TokenError, bearer, id_token_for
from dispositions import get_disposition, get_disposition_decision
from firebase_app import PROJECT_ID, get_db
from items import get_item
from membership import (
    accept_invite,
    create_auth_user,
    get_membership,
    invite_to_estate,
    membership_id,
)
from models import (
    EstateMembership,
    ItemStatus,
    MembershipRole,
    ResolutionType,
    SuggestedDisposition,
)
from resolutions import get_resolution
from test_claims import ESTATE_ID, reset_item
from test_dispositions import clear_decision
from test_resolutions import clear_resolution


from test_guard import require_destructive_ok

require_destructive_ok(__name__, "test_endpoints.py", "the test-ep-* items, memberships, resolutions and dispositions")

EXECUTOR_EMAIL = "steward-test-executor@example.com"
BENEFICIARY_EMAIL = "steward-test-beneficiary@example.com"
# No membership on this estate — the "authenticated but unauthorized" actor.
STRANGER_EMAIL = "steward-test-stranger@example.com"
# Invited during the run, so /accept has a real pending invite to accept.
INVITEE_EMAIL = "steward-test-invitee@example.com"

ITEM_CLAIM = "test-ep-claim"
ITEM_RESOLVE = "test-ep-resolve"
ITEM_DISPOSE = "test-ep-dispose"
ITEM_CONFLICT = "test-ep-conflict"
ALL_ITEMS = [ITEM_CLAIM, ITEM_RESOLVE, ITEM_DISPOSE, ITEM_CONFLICT]

CATEGORY = "test-endpoint-category"

client = TestClient(app)
failures: list[str] = []


def check(label: str, actual, expected) -> None:
    def show(value):
        return value.value if hasattr(value, "value") else value

    if actual == expected:
        print(f"  ok       {label}: {show(actual)}")
    else:
        failures.append(f"{label}: got {show(actual)!r}, expected {show(expected)!r}")
        print(f"  FAIL     {label}: got {show(actual)!r}, expected {show(expected)!r}")


def status(response, label: str, expected: int) -> None:
    check(label, response.status_code, expected)
    if response.status_code != expected:
        print(f"           body: {response.text[:200]}")


def clear_membership(user_id: str) -> None:
    get_db().collection(EstateMembership.COLLECTION).document(
        membership_id(ESTATE_ID, user_id)
    ).delete()


def clear_claims(item_id: str) -> None:
    db = get_db()
    for claim in get_claims_for_item(item_id):
        db.collection("claims").document(claim.id).delete()


def reset(item_id: str) -> None:
    reset_item(item_id, CATEGORY, "Seeded for the endpoint test.")
    clear_resolution(item_id)
    clear_decision(item_id)


def main() -> int:
    print(f"Project: {PROJECT_ID}")
    print(f"Estate:  {ESTATE_ID}\n")

    # --- setup -------------------------------------------------------------
    print("setup")
    executor_uid = create_auth_user(EXECUTOR_EMAIL, "Test Executor")
    invite_to_estate(ESTATE_ID, EXECUTOR_EMAIL, MembershipRole.EXECUTOR)
    accept_invite(ESTATE_ID, executor_uid)

    beneficiary_uid = create_auth_user(BENEFICIARY_EMAIL, "Test Beneficiary")
    invite_to_estate(ESTATE_ID, BENEFICIARY_EMAIL, MembershipRole.BENEFICIARY)
    accept_invite(ESTATE_ID, beneficiary_uid)

    stranger_uid = create_auth_user(STRANGER_EMAIL, "Test Stranger")
    clear_membership(stranger_uid)          # no role on this estate, ever

    invitee_uid = create_auth_user(INVITEE_EMAIL, "Test Invitee")
    clear_membership(invitee_uid)           # so /invite and /accept do real work

    executor = bearer(EXECUTOR_EMAIL)
    beneficiary = bearer(BENEFICIARY_EMAIL)
    stranger = bearer(STRANGER_EMAIL)
    invitee = bearer(INVITEE_EMAIL)
    print(f"  executor     {executor_uid}")
    print(f"  beneficiary  {beneficiary_uid}")
    print(f"  stranger     {stranger_uid}  (no membership)")
    print(f"  invitee      {invitee_uid}  (no membership yet)")

    for item_id in ALL_ITEMS:
        reset(item_id)
        clear_claims(item_id)
    print(f"  items        {', '.join(ALL_ITEMS)} (all unclaimed)\n")

    # --- authentication ----------------------------------------------------
    print("authentication")
    status(client.get(f"/estates/{ESTATE_ID}/items"), "no token", 401)
    status(
        client.get(f"/estates/{ESTATE_ID}/items",
                   headers={"Authorization": "Bearer not-a-real-token"}),
        "garbage token", 401,
    )
    status(
        client.get(f"/estates/{ESTATE_ID}/items", headers={"Authorization": "Basic abc"}),
        "wrong scheme", 401,
    )
    status(client.get("/healthz"), "healthz needs no token", 200)
    print()

    # --- POST /estates/{id}/invite -----------------------------------------
    print("POST /estates/{estate_id}/invite")
    denied = client.post(f"/estates/{ESTATE_ID}/invite", headers=beneficiary,
                         json={"email": INVITEE_EMAIL})
    status(denied, "beneficiary invites", 403)
    check("  nothing written", get_membership(ESTATE_ID, invitee_uid), None)

    denied = client.post(f"/estates/{ESTATE_ID}/invite", headers=stranger,
                         json={"email": INVITEE_EMAIL})
    status(denied, "stranger invites", 403)
    check("  nothing written", get_membership(ESTATE_ID, invitee_uid), None)

    allowed = client.post(f"/estates/{ESTATE_ID}/invite", headers=executor,
                          json={"email": INVITEE_EMAIL, "role": "beneficiary"})
    status(allowed, "executor invites", 200)
    if allowed.status_code == 200:
        check("  accepted", allowed.json()["accepted"], False)
    stored = get_membership(ESTATE_ID, invitee_uid)
    check("  membership written", stored is not None, True)
    if stored:
        check("  still pending", stored.accepted_at, None)
    print()

    # --- POST /estates/{id}/accept -----------------------------------------
    print("POST /estates/{estate_id}/accept")
    denied = client.post(f"/estates/{ESTATE_ID}/accept", headers=stranger)
    status(denied, "stranger with no invite", 404)
    check("  nothing written", get_membership(ESTATE_ID, stranger_uid), None)

    allowed = client.post(f"/estates/{ESTATE_ID}/accept", headers=invitee)
    status(allowed, "invitee accepts their own", 200)
    if allowed.status_code == 200:
        check("  accepted", allowed.json()["accepted"], True)
    accepted = get_membership(ESTATE_ID, invitee_uid)
    check("  accepted_at set", accepted is not None and accepted.accepted_at is not None, True)
    print()

    # --- GET /estates/{id}/items -------------------------------------------
    print("GET /estates/{estate_id}/items")
    status(client.get(f"/estates/{ESTATE_ID}/items", headers=stranger), "stranger lists", 403)

    listed = client.get(f"/estates/{ESTATE_ID}/items", headers=beneficiary)
    status(listed, "member lists", 200)
    if listed.status_code == 200:
        body = listed.json()
        ids = {row["id"] for row in body["items"]}
        check("  count matches items", body["count"], len(body["items"]))
        check("  seeded items present", set(ALL_ITEMS) <= ids, True)
        check("  only this estate", {row["estate_id"] for row in body["items"]}, {ESTATE_ID})
    print()

    # --- POST /items/{id}/claim --------------------------------------------
    print("POST /items/{item_id}/claim")
    denied = client.post(f"/items/{ITEM_CLAIM}/claim", headers=stranger, json={})
    status(denied, "stranger claims", 403)
    check("  nothing written", len(get_claims_for_item(ITEM_CLAIM)), 0)
    check("  item untouched", get_item(ITEM_CLAIM).status, ItemStatus.UNCLAIMED)

    status(client.post("/items/no-such-item/claim", headers=beneficiary, json={}),
           "unknown item", 404)

    allowed = client.post(f"/items/{ITEM_CLAIM}/claim", headers=beneficiary,
                          json={"comment": "Grandma promised me these."})
    status(allowed, "member claims", 200)
    if allowed.status_code == 200:
        check("  item_status", allowed.json()["item_status"], "claimed")
        check("  claimant is the caller", allowed.json()["user_id"], beneficiary_uid)
    check("  claim written", len(get_claims_for_item(ITEM_CLAIM)), 1)
    check("  item now claimed", get_item(ITEM_CLAIM).status, ItemStatus.CLAIMED)
    print()

    # --- POST /items/{id}/resolve ------------------------------------------
    print("POST /items/{item_id}/resolve")
    client.post(f"/items/{ITEM_RESOLVE}/claim", headers=beneficiary, json={})

    denied = client.post(f"/items/{ITEM_RESOLVE}/resolve", headers=beneficiary,
                         json={"resolution_type": "assigned_to_claimant",
                               "resolved_to_user_id": beneficiary_uid})
    status(denied, "beneficiary resolves", 403)
    check("  nothing written", get_resolution(ITEM_RESOLVE), None)
    check("  item untouched", get_item(ITEM_RESOLVE).status, ItemStatus.CLAIMED)

    conflict = client.post(f"/items/{ITEM_CONFLICT}/resolve", headers=executor,
                           json={"resolution_type": "executor_override"})
    status(conflict, "executor resolves an unclaimed item", 409)
    check("  nothing written", get_resolution(ITEM_CONFLICT), None)

    allowed = client.post(f"/items/{ITEM_RESOLVE}/resolve", headers=executor,
                          json={"resolution_type": "assigned_to_claimant",
                                "resolved_to_user_id": beneficiary_uid,
                                "notes": "Agreed at the kitchen table."})
    status(allowed, "executor resolves", 200)
    if allowed.status_code == 200:
        check("  item_status", allowed.json()["item_status"], "resolved")
    check("  resolution written", get_resolution(ITEM_RESOLVE) is not None, True)
    check("  item now resolved", get_item(ITEM_RESOLVE).status, ItemStatus.RESOLVED)
    print()

    # --- POST /items/{id}/disposition --------------------------------------
    print("POST /items/{item_id}/disposition")
    client.post(f"/items/{ITEM_DISPOSE}/claim", headers=beneficiary, json={})
    client.post(f"/items/{ITEM_DISPOSE}/resolve", headers=executor,
                json={"resolution_type": "assigned_to_claimant",
                      "resolved_to_user_id": beneficiary_uid})

    denied = client.post(f"/items/{ITEM_DISPOSE}/disposition", headers=beneficiary,
                         json={"executor_chosen_disposition": "donate"})
    status(denied, "beneficiary decides", 403)
    check("  no disposition", get_disposition(ITEM_DISPOSE), None)
    check("  no override log", get_disposition_decision(ITEM_DISPOSE), None)

    conflict = client.post(f"/items/{ITEM_CLAIM}/disposition", headers=executor,
                           json={"executor_chosen_disposition": "donate"})
    status(conflict, "executor decides on an unresolved item", 409)
    check("  no disposition", get_disposition(ITEM_CLAIM), None)
    check("  no override log", get_disposition_decision(ITEM_CLAIM), None)

    conflict = client.post(f"/items/{ITEM_DISPOSE}/disposition", headers=executor,
                           json={"executor_chosen_disposition": "uncertain"})
    status(conflict, "'uncertain' is not a decision", 409)
    check("  no disposition", get_disposition(ITEM_DISPOSE), None)

    allowed = client.post(f"/items/{ITEM_DISPOSE}/disposition", headers=executor,
                          json={"executor_chosen_disposition": "donate"})
    status(allowed, "executor decides", 200)
    if allowed.status_code == 200:
        check("  channel", allowed.json()["channel"], "donate")
        check("  status", allowed.json()["status"], "pending")
    check("  disposition written", get_disposition(ITEM_DISPOSE) is not None, True)
    check("  override log written", get_disposition_decision(ITEM_DISPOSE) is not None, True)
    print()

    # --- the agent route, now behind auth ----------------------------------
    print("POST /items/{item_id}/agent-message")
    status(client.post(f"/items/{ITEM_CLAIM}/agent-message"), "no token", 401)
    status(client.post(f"/items/{ITEM_CLAIM}/agent-message", headers=stranger),
           "stranger", 403)
    status(client.post(f"/items/{ITEM_CLAIM}/agent-message", headers=beneficiary),
           "member, but item is claimed", 409)
    print()

    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("OK — every endpoint authorized correctly, and every refusal wrote nothing.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except TokenError as exc:
        print(f"\nTokenError: {exc}")
        sys.exit(2)
