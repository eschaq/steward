"""A fast look at a photograph before it costs anything to classify.

Catches the three uploads that are obviously not worth a Gemini call — too
dark, too blurry, or an empty frame — so the person can retake the picture in
the moment rather than waiting through a full classification to be told the
agent couldn't see anything.

**Why this is not Gemma, which is what was asked for.** Checked both routes on
2026-08-17: Gemma is in Vertex Model Garden as an *open* model
(`publishers/google/models/gemma3`, `gemma3n`, `shieldgemma2`), and every one of
them reports `supportedActions: [openNotebook, deploy, deployGke,
multiDeployVertex]` — deploy-only, no serverless `predict`. Standing one up
needs a `g2-standard-12` / NVIDIA L4 endpoint at minimum, which bills
continuously whether or not anyone uploads a photo, needs GPU quota, and adds
cold-start latency to the very thing it is supposed to make faster. The Gemini
API route would work but needs the AI Studio key CLAUDE.md records as
deliberately removed. This project has no deployed endpoints.

So this is arithmetic rather than a model, and for this particular question that
is the better tool, not merely the cheaper one: "too dark", "too blurry" and
"empty frame" are measurable properties of the pixels. A vision model asked the
same question would give a slower, less repeatable answer to something a
histogram already knows. It runs in single-digit milliseconds, costs nothing,
needs no network, and cannot rate-limit.

What it is **not** is a judgement about whether a photograph is any good. It has
one job: spot the frames a classifier will certainly fail on.
"""

import io
import logging
import time
from typing import NamedTuple, Optional

from PIL import Image, ImageFilter, ImageStat

logger = logging.getLogger(__name__)

# Long edge the image is reduced to before measuring. Everything here is a
# global statistic, so a small copy answers the same question far faster — and
# blur survives downscaling as long as we don't go too small.
SAMPLE_EDGE = 640

# --- thresholds, calibrated against the classifier rather than by eye --------
#
# These were set by degrading a real photograph of a real armchair and asking
# gemini-3.5-flash what it made of each version. The headline finding is that
# **Gemini is far more tolerant than it looks**:
#
#   brightness 202 (clean)   -> 'armchair' 0.95
#   brightness  63 (v. dark) -> 'armchair' 0.95     <- still fine
#   sharpness  2543 (clean)  -> 'armchair' 0.95
#   sharpness   2.9 (blur 12)-> 'armchair' 0.85     <- still fine
#   sharpness   2.4 (blur 30)-> 'unknown'  0.10     <- finally breaks
#   contrast    0.0 (blank)  -> 'unknown'  0.00     <- reliably broken
#
# So a "sensible-looking" blur threshold in the tens would have flagged pictures
# the classifier reads perfectly, which is exactly the trap this is supposed to
# avoid: a convenience layer that interrupts someone holding a good photograph
# is worse than no layer. Everything below is therefore set at the point of
# *demonstrated* failure with margin, not at the point where a photo starts
# looking poor.
#
# The consequence worth stating: this catches much less than a photo-quality
# check normally would. That is the correct amount for this pipeline.

# Essentially black. Gemini still managed 0.95 at 63, so this sits far below.
TOO_DARK = 25.0
# Evidenced: 247 broke it, 236 was already unusable, 220 was not the problem
# (that test frame failed on content, not exposure).
TOO_BRIGHT = 244.0

# Variance of the Laplacian, the standard sharpness measure. The observed
# boundary is between 2.9 (readable) and 2.4 (not), which is too narrow to
# trust — so this sits at the failing side and will only ever catch a frame
# with no recoverable detail at all.
TOO_BLURRY = 2.6

# Standard deviation of luminance. The one signal that is both reliable and
# decisive: a photograph of anything has tonal range, and a lens cap, a wall or
# a blank export does not. The blank test frame measures 0.0.
TOO_FLAT = 3.0


class Verdict(NamedTuple):
    """What we think of the picture, and what to say about it.

    `ok` False means "worth asking whether they want to retake it" — never
    "refused". The caller is expected to offer, not enforce; see the note on
    `should_offer_retake`.
    """

    ok: bool
    # A short machine-readable tag: dark | bright | blurry | blank | unreadable.
    problem: Optional[str]
    # Plain language, addressed to the person who just took the photo.
    message: Optional[str]
    # The measurements, so a puzzling verdict can be argued with.
    brightness: Optional[float] = None
    sharpness: Optional[float] = None
    contrast: Optional[float] = None
    took_ms: Optional[float] = None


def _laplacian_variance(grey: Image.Image) -> float:
    """Sharpness. Convolve with a Laplacian kernel and take the variance.

    An edge-detection pass leaves a lot of signal in a sharp image and very
    little in a blurred one, so the spread of the result is a good proxy for
    focus. Pillow's FIND_EDGES is a 3x3 Laplacian; `stddev ** 2` is the variance
    the literature refers to.
    """
    edges = grey.filter(ImageFilter.FIND_EDGES)
    # Drop the 1px border, which FIND_EDGES leaves as an artefact bright frame
    # that would otherwise flatter a blurry picture.
    w, h = edges.size
    if w > 4 and h > 4:
        edges = edges.crop((2, 2, w - 2, h - 2))
    return float(ImageStat.Stat(edges).stddev[0] ** 2)


def inspect(data: bytes) -> Verdict:
    """Look at an uploaded photograph. Never raises.

    An image this cannot even open comes back `ok=True` with problem
    `unreadable`: deciding a file is broken is the classifier's job and the
    upload path's, not this one's. Failing open is the whole point — a
    convenience layer that blocks a good photograph is worse than no layer.
    """
    started = time.perf_counter()
    try:
        image = Image.open(io.BytesIO(data))
        image.draft("L", (SAMPLE_EDGE, SAMPLE_EDGE))  # cheap JPEG downscale-on-decode
        grey = image.convert("L")
        grey.thumbnail((SAMPLE_EDGE, SAMPLE_EDGE), Image.Resampling.BILINEAR)

        stat = ImageStat.Stat(grey)
        brightness = float(stat.mean[0])
        contrast = float(stat.stddev[0])
        sharpness = _laplacian_variance(grey)
    except Exception:  # noqa: BLE001 — every failure degrades to "carry on"
        logger.exception("photo pre-check could not read the image")
        return Verdict(True, "unreadable", None,
                       took_ms=(time.perf_counter() - started) * 1000)

    took = (time.perf_counter() - started) * 1000
    common = {"brightness": round(brightness, 1), "sharpness": round(sharpness, 1),
              "contrast": round(contrast, 1), "took_ms": round(took, 1)}

    # Order matters: a dark frame is usually also flat and soft, and being told
    # "it's dark" is more actionable than "it's low contrast".
    if brightness < TOO_DARK:
        return Verdict(False, "dark",
                       "This one's come out very dark — want to try again with "
                       "a bit more light?", **common)
    if brightness > TOO_BRIGHT:
        return Verdict(False, "bright",
                       "This one's washed out — want to try again out of the "
                       "direct light?", **common)
    if contrast < TOO_FLAT:
        return Verdict(False, "blank",
                       "There doesn't seem to be much in this one — want to try "
                       "again?", **common)
    if sharpness < TOO_BLURRY:
        return Verdict(False, "blurry",
                       "This one's a bit out of focus — want to try again?",
                       **common)

    return Verdict(True, None, None, **common)


def should_offer_retake(verdict: Verdict) -> bool:
    """Whether the UI should pause and ask, rather than carry straight on.

    `unreadable` deliberately does not qualify: if this could not read the file
    it has no opinion, and an opinion is the only thing worth interrupting
    someone for.
    """
    return not verdict.ok and verdict.problem != "unreadable"
