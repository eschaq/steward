"""Real Firebase ID tokens for the test scripts.

The API verifies tokens with the Admin SDK, so testing it honestly means minting
tokens the same way a browser would: sign a test user in against Identity
Toolkit and use the `idToken` it returns. Nothing here is mocked.

`auth.create_custom_token` would be the tidier route, but it needs a service
account to sign with, and this machine authenticates as a user — so the
email/password sign-in flow is what's left.

**Test accounts only.** `id_token_for` refuses any address outside
@example.com, because it sets the account's password to do its job and must
never do that to a real person's account.
"""

import json
import os
import subprocess
import urllib.request
from typing import Optional

from firebase_admin import auth

from firebase_app import PROJECT_ID, get_app

# Fixed, and fine to be: these accounts exist only on this hackathon project and
# hold nothing. The key below is a browser key, public by design in any Firebase
# web app.
TEST_PASSWORD = "steward-test-pw-2026"
TEST_EMAIL_SUFFIX = "@example.com"

_API_KEY: Optional[str] = None
_TOKENS: dict[str, str] = {}


class TokenError(Exception):
    """A test token could not be minted."""


def web_api_key() -> str:
    """The project's browser API key, from the environment or from gcloud.

    Not committed anywhere: set STEWARD_WEB_API_KEY to skip the gcloud call.
    """
    global _API_KEY
    if _API_KEY:
        return _API_KEY

    from_env = os.environ.get("STEWARD_WEB_API_KEY")
    if from_env:
        _API_KEY = from_env
        return _API_KEY

    try:
        listed = subprocess.run(
            ["gcloud", "services", "api-keys", "list", "--project", PROJECT_ID,
             "--format=value(name)"],
            capture_output=True, text=True, timeout=120, check=True,
        ).stdout.split()
        if not listed:
            raise TokenError(f"No API keys on project {PROJECT_ID}.")
        _API_KEY = subprocess.run(
            ["gcloud", "services", "api-keys", "get-key-string", listed[0],
             "--format=value(keyString)"],
            capture_output=True, text=True, timeout=120, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise TokenError(
            "Could not read the web API key. Set STEWARD_WEB_API_KEY, or make "
            f"`gcloud` available and authenticated for {PROJECT_ID}. ({exc})"
        ) from exc

    if not _API_KEY:
        raise TokenError("gcloud returned an empty API key string.")
    return _API_KEY


def id_token_for(email: str, display_name: Optional[str] = None) -> str:
    """A real, verifiable ID token for a test user, creating the account if needed.

    Cached per email for the life of the process — signing in on every request
    would be slow and pointless.
    """
    if not email.endswith(TEST_EMAIL_SUFFIX):
        raise TokenError(
            f"{email} is not a {TEST_EMAIL_SUFFIX} address. This sets the "
            "account's password, so it is for test accounts only."
        )

    if email in _TOKENS:
        return _TOKENS[email]

    get_app()
    try:
        record = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        record = auth.create_user(
            email=email, display_name=display_name or email.split("@")[0]
        )
    auth.update_user(record.uid, password=TEST_PASSWORD)

    request = urllib.request.Request(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={web_api_key()}",
        data=json.dumps(
            {"email": email, "password": TEST_PASSWORD, "returnSecureToken": True}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
    except Exception as exc:  # noqa: BLE001 — surfaced as TokenError either way
        raise TokenError(f"Sign-in failed for {email}: {exc}") from exc

    token = body.get("idToken")
    if not token:
        raise TokenError(f"Sign-in for {email} returned no idToken.")

    _TOKENS[email] = token
    return token


def bearer(email: str, display_name: Optional[str] = None) -> dict[str, str]:
    """Authorization header for a test user."""
    return {"Authorization": f"Bearer {id_token_for(email, display_name)}"}
