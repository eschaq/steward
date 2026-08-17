"""A deliberate step between running a test script and it rewriting real data.

Every suite in this directory runs against **real Firestore** — that is the
point of them, and it is why they catch things an emulator would not. It is
also why a stray run is destructive: they reset fixtures with full document
overwrites, delete claims, and clear resolutions and dispositions.

That is not hypothetical. On 2026-08-17 a routine regression sweep — run to
check an unrelated change — overwrote `test-resolve-unclaimed` and wiped a
resolution someone had created through the live app. The fixture timestamps
recorded it precisely: nine items restamped inside a thirty-second window.

The failure mode was not carelessness. It was that running the suite is
one command and its blast radius is invisible at the moment you type it. So
this makes the destructive intent explicit rather than relying on remembering:

    STEWARD_ALLOW_DESTRUCTIVE_TESTS=1 .venv/bin/python test_claims.py

Guarding *every* suite rather than only the obviously destructive ones is
deliberate. Deciding per-file which ones "really" write is exactly the judgement
call that goes wrong under deadline pressure, and the cost of being wrong is
demo data. The friction is identical either way: one variable.
"""

import os
import sys

ENV_VAR = "STEWARD_ALLOW_DESTRUCTIVE_TESTS"


def require_destructive_ok(
    module_name: str, suite: str, touches: str = "shared fixtures"
) -> None:
    """Stop unless the caller has said out loud that this may write real data.

    `module_name` is the caller's `__name__`, and the guard only fires for the
    script actually being run. Several suites import each other for their
    fixtures — `test_resolutions` uses `test_claims`'s `reset_item` — and
    without this check the imported module's guard would fire first and name the
    wrong file. Importing a suite does no Firestore work; only `main()` does.

    Exits 3 — distinct from 1 (a real failure) and 2 (blocked by an upstream
    service), so a wrapper can tell "refused to run" apart from "ran and
    something is broken".
    """
    if module_name != "__main__":
        return
    if os.environ.get(ENV_VAR, "").strip() in ("1", "true", "yes"):
        return

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "steward-hackathon-505217")
    print(
        f"\n  {suite} writes to real Firestore and was not run.\n\n"
        f"  Project : {project}\n"
        f"  Resets  : {touches}\n\n"
        f"  That means full document overwrites, deleted claims and cleared\n"
        f"  resolutions. Anything created through the live app on those\n"
        f"  fixtures is lost.\n\n"
        f"  If that is what you want:\n\n"
        f"      {ENV_VAR}=1 .venv/bin/python {suite}\n\n"
        f"  Close to a demo, prefer not to. Re-seed afterwards with\n"
        f"  seed_demo_items.py if you do.\n",
        file=sys.stderr,
    )
    raise SystemExit(3)
