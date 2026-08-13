"""Firebase ID token verification, as a FastAPI dependency.

The Firebase Auth uid *is* the User.id (see membership.py), so a verified token
hands route handlers exactly the identifier `require_role` wants — no lookup, no
mapping table.

This establishes *who* the caller is and nothing more. Authorization stays where
it already lives: `require_role` inside membership.py, and the state gates inside
resolutions.py and dispositions.py. A route that re-decided those questions would
be a second, drifting copy of the rules.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth

from firebase_app import get_app

# Tokens are rejected if they look issued in the future. A second of drift
# between this host and Google's clock is ordinary and shouldn't read as a
# forged token; anything beyond this still fails.
CLOCK_SKEW_SECONDS = 30

# auto_error=False so a missing header raises our own 401 with a useful message
# rather than FastAPI's bare 403.
_bearer = HTTPBearer(auto_error=False, description="Firebase ID token")


def current_uid(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """The verified caller's Firebase uid, or 401.

    Every failure here is a 401 with a plain reason — an expired token, a token
    from another project, and a missing header are different problems, and a
    caller debugging their integration should be able to tell them apart.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing bearer token. Send a Firebase ID token as `Authorization: Bearer <token>`.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    get_app()
    try:
        decoded = auth.verify_id_token(
            credentials.credentials, clock_skew_seconds=CLOCK_SKEW_SECONDS
        )
    except auth.ExpiredIdTokenError as exc:
        raise HTTPException(status_code=401, detail="ID token has expired.") from exc
    except auth.RevokedIdTokenError as exc:
        raise HTTPException(status_code=401, detail="ID token has been revoked.") from exc
    except (auth.InvalidIdTokenError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=f"Invalid ID token: {exc}") from exc

    uid = decoded.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="ID token carries no uid.")
    return uid


# What route handlers annotate with: `uid: CallerUid`.
CallerUid = Annotated[str, Depends(current_uid)]
