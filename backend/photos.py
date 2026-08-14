"""Item photographs, stored in Cloud Storage.

Item.photo_urls is defined by docs/estate-agent-data-model.md; this fills it.
Nothing else about the entity changes.

**Public-read objects with unguessable paths, not signed URLs.** Two reasons:

  * Signed URLs need something to sign with. This project authenticates as a
    user (Application Default Credentials, no service-account key), so
    `generate_signed_url` has no private key available and would need an IAM
    signBlob round trip and a service account to impersonate.
  * A signed URL expires. `photo_urls` is a stored field the dashboard and the
    review table read directly, so a URL that dies after an hour would mean
    minting fresh ones on every read — a different shape from what the data
    model describes.

Each object gets a `uuid4` in its path, so a URL cannot be guessed from an item
id. That is the same practical property a Firebase download token gives.

⚠️ It is still **public to anyone holding the link**, and these are a grieving
family's belongings. Acceptable for a demo on a private project; it is not the
right answer for real estates. See the note at the bottom of backend/README.md.
"""

import uuid
from typing import Optional

from google.cloud import storage

from firebase_app import PROJECT_ID

BUCKET_NAME = f"{PROJECT_ID}-item-photos"

# What a browser will actually render, and what a phone camera produces.
ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}

# Generous for a photograph, small enough that one upload cannot fill a disk.
MAX_BYTES = 12 * 1024 * 1024

_CLIENT: Optional[storage.Client] = None


class PhotoError(Exception):
    """The upload could not be accepted, and why — never a silent drop."""


def _bucket() -> storage.Bucket:
    """The photo bucket, with the client built once per process."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = storage.Client(project=PROJECT_ID)
    return _CLIENT.bucket(BUCKET_NAME)


def object_path(item_id: str, extension: str) -> str:
    """Where one photograph lives.

    The uuid is the whole security model for the URL: item ids are predictable
    (`demo-hall-rug`), so without it anyone could guess a photograph's address.
    """
    return f"items/{item_id}/{uuid.uuid4().hex}.{extension}"


def store_item_photo(item_id: str, data: bytes, content_type: Optional[str]) -> str:
    """Put one photograph in Cloud Storage and return its public URL.

    Raises PhotoError for anything it will not accept, so the caller can say
    plainly what was wrong rather than failing at render time.
    """
    if not data:
        raise PhotoError("That file was empty.")
    if len(data) > MAX_BYTES:
        raise PhotoError(
            f"That photo is {len(data) / 1024 / 1024:.1f}MB. "
            f"The limit is {MAX_BYTES // 1024 // 1024}MB — try a smaller one?"
        )

    normalized = (content_type or "").split(";")[0].strip().lower()
    if normalized not in ALLOWED_TYPES:
        raise PhotoError(
            f"That looks like {normalized or 'an unknown file type'}. "
            f"Photos need to be one of: {', '.join(sorted(ALLOWED_TYPES))}."
        )

    blob = _bucket().blob(object_path(item_id, ALLOWED_TYPES[normalized]))
    blob.upload_from_string(data, content_type=normalized)
    # Bucket-level IAM already grants allUsers objectViewer, so there is no
    # per-object ACL to set — uniform bucket-level access forbids those anyway.
    return blob.public_url
