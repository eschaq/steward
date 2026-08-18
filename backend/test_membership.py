"""End-to-end check of the invite/accept/role-check path against the real project.

Not a test suite — a script. It creates two Firebase Auth users, invites both to
the seed estate, accepts both invites, and prints the role the role-check helper
returns for each.

Usage:
    .venv/bin/python test_membership.py
"""

import sys

from firebase_app import PROJECT_ID
from membership import (
    MembershipError,
    estates_for_user,
    pending_invitations_for_user,
    accept_invite,
    create_auth_user,
    get_membership,
    get_role,
    invite_to_estate,
)
from models import MembershipRole


from test_guard import require_destructive_ok

require_destructive_ok(__name__, "test_membership.py", "test-account memberships on the seeded estate")

ESTATE_ID = "seed-estate-001"
# Its own address: this one is invited and accepted every run, and must not
# collide with the two in PEOPLE above.
FINDER_EMAIL = "steward-test-finder@example.com"

PEOPLE = [
    ("steward-test-executor@example.com", "Test Executor", MembershipRole.EXECUTOR),
    (
        "steward-test-beneficiary@example.com",
        "Test Beneficiary",
        MembershipRole.BENEFICIARY,
    ),
]


def main() -> int:
    print(f"Project: {PROJECT_ID}")
    print(f"Estate:  {ESTATE_ID}\n")

    failures = []

    for email, display_name, expected_role in PEOPLE:
        print(f"{email}")

        uid = create_auth_user(email, display_name)
        print(f"  auth user      uid={uid}")

        membership = invite_to_estate(ESTATE_ID, email, expected_role)
        pending = get_membership(ESTATE_ID, uid)
        print(
            f"  invited        role={membership.role.value} "
            f"accepted_at={pending.accepted_at}"
        )

        # A pending invite must grant no role yet.
        role_before = get_role(uid, ESTATE_ID)
        if role_before is not None and pending.accepted_at is None:
            failures.append(f"{email}: pending invite granted role {role_before.value}")
            print(f"  FAIL           pending invite granted role {role_before.value}")

        accepted = accept_invite(ESTATE_ID, uid)
        print(f"  accepted       accepted_at={accepted.accepted_at}")

        role = get_role(uid, ESTATE_ID)
        printed = role.value if role else "none"
        if role == expected_role:
            print(f"  role check     {printed}  (expected {expected_role.value})\n")
        else:
            failures.append(
                f"{email}: role check returned {printed}, expected {expected_role.value}"
            )
            print(f"  FAIL           {printed}, expected {expected_role.value}\n")

    # The invitation has to be *findable* before it can be accepted.
    #
    # The regression this guards: `/me/estates` returns accepted memberships
    # only, so for a while a freshly invited account was indistinguishable from
    # an account with nothing — the browser sent it to "create your own estate"
    # while a real invitation sat unanswered. Nothing could have told it
    # otherwise; `get_role` hides pending rows by design, and `GET /me` can only
    # report invite_pending for an estate the caller already names, which is
    # precisely what an invitee does not know.
    finder = create_auth_user(FINDER_EMAIL, "Test Finder")
    invite_to_estate(ESTATE_ID, FINDER_EMAIL, MembershipRole.BENEFICIARY)
    listed = [e.id for e, _ in pending_invitations_for_user(finder)]
    belongs = [e.id for e, _ in estates_for_user(finder)]
    if ESTATE_ID in listed and ESTATE_ID not in belongs:
        print(f"{FINDER_EMAIL}\n  pending invite is discoverable, and grants nowhere to go yet")
    else:
        failures.append("a pending invite was not discoverable before accepting")
        print(f"  FAIL           pending invite not discoverable (pending={listed})")

    accept_invite(ESTATE_ID, finder)
    listed = [e.id for e, _ in pending_invitations_for_user(finder)]
    belongs = [e.id for e, _ in estates_for_user(finder)]
    if ESTATE_ID not in listed and ESTATE_ID in belongs:
        print("  and once accepted it moves to the estates they belong to\n")
    else:
        failures.append("accepting an invite did not move it out of pending")
        print(f"  FAIL           still pending after accepting (pending={listed})\n")

    # A stranger has no role on this estate.
    stranger_role = get_role("no-such-uid", ESTATE_ID)
    if stranger_role is None:
        print("non-member       role check returned none, as expected")
    else:
        failures.append(f"non-member got role {stranger_role.value}")
        print(f"FAIL             non-member got role {stranger_role.value}")

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nOK — both users invited, accepted, and role-checked correctly.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MembershipError as exc:
        print(f"\nMembershipError: {exc}")
        sys.exit(1)
