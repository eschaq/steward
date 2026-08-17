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
