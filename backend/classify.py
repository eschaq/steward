"""Item photo classification on Vertex AI, via the `google-genai` SDK.

Transport is Vertex AI with Application Default Credentials — no API key, no
`.env`. (It was the direct Gemini API with an AI Studio key until Blaze billing
was enabled on the project.) The SDK arrived with `google-adk`, so this added no
dependency.

Returns exactly the four `ai_*` fields defined for Item in
docs/estate-agent-data-model.md — nothing invented, nothing omitted.

Failure handling follows the RDD: a failed or unparseable classification does
not block the upload and never silently guesses. It comes back as confidence
0.0 with a plain-language note, which routes the item to
`needs_clarification` through the same threshold every other item goes through.
"""

import json
import mimetypes
import os
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

from firebase_app import PROJECT_ID
from models import ItemStatus

# Gemini Flash by default; Pro is reserved for complex final reasoning (CLAUDE.md).
DEFAULT_MODEL = "gemini-3.5-flash"

# Vertex serves gemini-3.5-flash from `global`, not from a named region — asking
# us-central1 for it returns 404 even though the project has access there (other
# models, e.g. gemini-2.5-flash, answer from us-central1 fine). Override with
# VERTEX_LOCATION if a future model is region-pinned.
DEFAULT_LOCATION = os.environ.get("VERTEX_LOCATION", "global")

# Below this, the agent asks instead of guessing (RDD failure-handling section).
CONFIDENCE_THRESHOLD = 0.6

# What the executor sees when the classifier could not do its job at all.
CLASSIFICATION_FAILED_NOTE = "Couldn't classify this one — take a look?"

def _response_schema() -> types.Schema:
    """Constrain generation to the four ai_* fields, so the model can't drift.

    Only ai_est_era_or_brand is nullable — the other three always come back.
    Same schema as before the Vertex move, in the `google-genai` type.
    """
    string = types.Schema(type=types.Type.STRING)
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "ai_category": string,
            "ai_condition_notes": string,
            "ai_est_era_or_brand": types.Schema(
                type=types.Type.STRING, nullable=True
            ),
            "ai_classification_confidence": types.Schema(type=types.Type.NUMBER),
        },
        required=[
            "ai_category",
            "ai_condition_notes",
            "ai_classification_confidence",
        ],
    )


PROMPT = """You are cataloguing the contents of a household estate, one photo at a time.

Identify the single main household item in this photo and reply with JSON only:

{
  "ai_category": "short lowercase noun phrase, e.g. \\"armchair\\", \\"dinnerware\\", \\"power tool\\"",
  "ai_condition_notes": "one or two plain sentences on visible condition — wear, damage, completeness. Describe only what you can actually see.",
  "ai_est_era_or_brand": "estimated era and/or brand if there is real visual evidence for it, otherwise null",
  "ai_classification_confidence": 0.0
}

About ai_classification_confidence: it is your calibrated probability, from 0.0
to 1.0, that ai_category correctly names the item. Be honest rather than
generous — a family is going to act on this.

If the photo does not show an identifiable household item at all — it is blank,
a solid colour, too blurry, too dark, or otherwise unreadable — set
ai_category to "unknown", say plainly in ai_condition_notes what you can and
cannot see, and give a confidence below 0.2. Do not guess at an item that
isn't clearly there."""


class Classification(BaseModel):
    """The four ai_* Item fields, plus why the agent is unsure (never persisted)."""

    ai_category: str
    ai_condition_notes: str
    ai_est_era_or_brand: Optional[str] = None
    ai_classification_confidence: float = Field(ge=0.0, le=1.0)

    # Set when the API call or its response failed outright, as opposed to the
    # model looking at the photo and honestly reporting low confidence. Kept off
    # the Item document — Item's shape is fixed by the data model doc.
    error: Optional[str] = None

    @property
    def status(self) -> ItemStatus:
        """Real routing logic: low confidence means ask, not guess."""
        if self.ai_classification_confidence < CONFIDENCE_THRESHOLD:
            return ItemStatus.NEEDS_CLARIFICATION
        return ItemStatus.UNCLAIMED

    @property
    def needs_clarification(self) -> bool:
        return self.status is ItemStatus.NEEDS_CLARIFICATION


_CLIENT: Optional[genai.Client] = None


def vertex_client() -> genai.Client:
    """A Vertex AI client on Application Default Credentials, built once.

    Public because marketplace.py needs the same client — one per process, not
    one per module.

    Cached deliberately: the client owns an httpx connection pool and closes it
    when collected, so a per-call client can be finalized out from under an
    in-flight request ("Cannot send a request, as the client has been closed").
    One per process, like the Firebase app.

    On Cloud Run the attached service account supplies credentials
    automatically; no key material is involved either way.
    """
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", PROJECT_ID),
            location=DEFAULT_LOCATION,
        )
    return _CLIENT


def model_name(override: Optional[str] = None) -> str:
    return override or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def _unreadable(reason: str) -> Classification:
    """A classification that failed, expressed as an honest low-confidence result."""
    return Classification(
        ai_category="unknown",
        ai_condition_notes=CLASSIFICATION_FAILED_NOTE,
        ai_est_era_or_brand=None,
        ai_classification_confidence=0.0,
        error=reason,
    )


def _parse_json_object(raw: str) -> Optional[dict]:
    """Parse the leading JSON object out of a model response.

    `raw_decode` stops at the end of the first complete object, so trailing
    noise — a stray closing brace, a stranded newline — doesn't throw away an
    otherwise good classification. Observed in practice: gemini-3.5-flash
    occasionally appends one extra `}`.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text.lstrip("`")
        text = text[4:] if text.startswith("json") else text
    try:
        payload, _ = json.JSONDecoder().raw_decode(text.strip())
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def classify_image(
    image_path: str | Path, model_override: Optional[str] = None
) -> Classification:
    """Classify the household item in `image_path`.

    Always returns a Classification. Transport, quota, and parse failures come
    back as confidence 0.0 with `error` set, so the caller's status logic routes
    them to needs_clarification rather than the upload failing.
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"No image at {path}")

    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"

    try:
        response = vertex_client().models.generate_content(
            model=model_name(model_override),
            contents=[
                PROMPT,
                types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_response_schema(),
            ),
        )
        raw = (response.text or "").strip()
    except Exception as exc:  # noqa: BLE001 — any failure degrades the same way
        return _unreadable(f"{type(exc).__name__}: {exc}")

    payload = _parse_json_object(raw)
    if payload is None:
        return _unreadable(f"model returned non-JSON: {raw[:200]}")

    # An empty-string era means "no evidence", same as null.
    if not payload.get("ai_est_era_or_brand"):
        payload["ai_est_era_or_brand"] = None

    try:
        return Classification.model_validate(
            {key: payload.get(key) for key in Classification.model_fields if key != "error"}
        )
    except ValidationError as exc:
        return _unreadable(f"response failed validation: {exc.errors()[0]['msg']}")


def status_for_confidence(confidence: float) -> ItemStatus:
    """Standalone form of the threshold, for callers holding a bare confidence."""
    if confidence < CONFIDENCE_THRESHOLD:
        return ItemStatus.NEEDS_CLARIFICATION
    return ItemStatus.UNCLAIMED
