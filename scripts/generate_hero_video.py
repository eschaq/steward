"""Generate the ambient hero clip for the arrival screens, once.

**A development script, not an app feature.** It is run by hand, the output is
committed to `frontend/public/brand/`, and nothing in the running product ever
calls Veo. Video generation is slow and costs real money per second; doing it
at request time would be both.

Talks to Vertex AI through the same project and Application Default Credentials
that `backend/classify.py` already uses for Gemini — no API key, no new auth
path, no second client pattern.

**Seeded with the existing photograph.** `hero-gable-landscape.jpg` is passed in
as the first frame rather than describing a roofline in words and hoping. That
guarantees the clip *is* the established image rather than a cousin of it, and
it means the static poster frame and the video's opening frame are the same
picture — so a browser that never loads the video shows exactly what the first
frame would have been.

Usage:
    cd backend && .venv/bin/python ../scripts/generate_hero_video.py
    cd backend && .venv/bin/python ../scripts/generate_hero_video.py --model veo-3.1-generate-001

There is no "Veo 3.1 Lite" published on Vertex; `veo-3.1-fast-generate-001` is
the cheap 3.1 tier and the default here.
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from firebase_app import PROJECT_ID  # noqa: E402

# Veo is served from a named region, unlike gemini-3.5-flash which answers from
# `global`. That is the one thing this script does differently from classify.py.
LOCATION = os.environ.get("VEO_LOCATION", "us-central1")
DEFAULT_MODEL = "veo-3.1-fast-generate-001"

BRAND = Path(__file__).resolve().parents[1] / "frontend" / "public" / "brand"
SEED_IMAGE = BRAND / "hero-gable-landscape.jpg"
OUTPUT = BRAND / "hero-gable.mp4"

# The first version of this prompt said "the camera is locked off and does not
# move", and the result was effectively a still: Veo's only change across the
# eight seconds was a global luminance ramp with no edge moving anywhere in
# frame. Under this design's 86%-opacity duotone and a scrim that reaches 97%
# over much of the picture, that reads as a photograph. Measured: mean
# frame-to-frame difference peaked at 12.8/255, all of it a uniform fade.
#
# So the camera moves now — very slowly, and in one direction only. A slow
# push-in gives *parallax*: the roofline edge travels against the brick behind
# it, which survives the scrim in a way a brightness change does not. Everything
# else is still held down hard, because Veo will otherwise reach for drifting
# cloud, lens flare and a title-sequence reveal.
# Used with --no-seed. Seeding from the existing still gave near-static output
# (Veo mostly re-lit the photograph rather than moving through it), so this
# describes the scene from nothing and asks for real camera travel. The building
# will not be the one in the stills — that is the trade.
TEXT_PROMPT = """Slow cinematic drift past the gable end of an old English stone cottage in late
afternoon. Weathered oak beams form the apex, hand-cut stone blocks below, worn
slate roof tiles catching low warm light.

The camera glides steadily and smoothly to the right and very slightly upward,
one continuous unbroken move at walking pace, as if on a dolly. Real parallax:
the roof edge passes across the stonework behind it. The move never stops,
never reverses, never speeds up.

Late golden hour. Warm terracotta, rust and deep brown tones, soft low contrast,
gentle shadow. Shallow depth of field. Calm, domestic, unhurried — an old house
at rest with nobody in it.

No people, no animals, no vehicles, no text, no titles, no captions, no
graphics, no logos, no watermark. No handheld shake, no zoom, no whip pan, no
orbit, no rack focus, no cuts. No lens flare, no sunbeams, no rain, no snow, no
fast-moving clouds."""

PROMPT = """A quiet shot of a weathered timber gable and old brick, late afternoon.

The camera pushes in extremely slowly and steadily — a very gradual, almost
imperceptible move closer over the whole clip, no more than a few percent. It is
one continuous, even movement with no easing, no stopping, and no change of
direction. Locked to a tripod on a slow motorised slider.

Otherwise the scene is completely still: no wind, no moving objects, no people.
The light stays constant.

Warm terracotta and deep brown tones, heavily duotoned, low contrast, soft and
shadowed. The mood is calm and domestic — an old house at rest, nobody in it.

No people, no text, no titles, no graphics, no logos. No handheld shake, no
zoom-out, no pan, no tilt, no orbit, no rack focus. No dramatic lighting
changes, no lens flare, no sunbeams, no birds, no rain, no drifting cloud.
Nothing enters or leaves the frame."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--seconds", type=int, default=8)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Generate from the prompt alone instead of the existing photograph.",
    )
    args = parser.parse_args()

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
    print(f"project  : {project}")
    print(f"location : {LOCATION}")
    print(f"model    : {args.model}")
    print(f"duration : {args.seconds}s")

    client = genai.Client(vertexai=True, project=project, location=LOCATION)

    image = None
    prompt = TEXT_PROMPT if args.no_seed else PROMPT
    if not args.no_seed:
        if not SEED_IMAGE.is_file():
            print(f"! no seed image at {SEED_IMAGE}", file=sys.stderr)
            return 1
        image = types.Image(
            image_bytes=SEED_IMAGE.read_bytes(), mime_type="image/jpeg"
        )
        print(f"seed     : {SEED_IMAGE.name} ({SEED_IMAGE.stat().st_size // 1024} KB)")

    config = types.GenerateVideosConfig(
        duration_seconds=args.seconds,
        number_of_videos=1,
        aspect_ratio="16:9",
        # The hero is muted in the browser, so paying to generate a soundtrack
        # nobody will hear would be waste on both counts.
        generate_audio=False,
    )

    print("\nasking Veo… (this takes a couple of minutes)")
    started = time.time()
    operation = client.models.generate_videos(
        model=args.model, prompt=prompt, image=image, config=config
    )

    while not operation.done:
        time.sleep(15)
        operation = client.operations.get(operation)
        print(f"  … {int(time.time() - started)}s")

    if getattr(operation, "error", None):
        print(f"\n! Veo returned an error: {operation.error}", file=sys.stderr)
        return 1

    videos = getattr(operation.response, "generated_videos", None) or []
    if not videos:
        print(f"\n! no video came back: {operation.response}", file=sys.stderr)
        return 1

    data = videos[0].video.video_bytes
    args.output.write_bytes(data)
    print(f"\nwrote {args.output}  ({len(data) / 1024 / 1024:.2f} MB) "
          f"in {int(time.time() - started)}s")
    print("\nCommit it: this is a build asset, served from the frontend's own "
          "origin like the stills beside it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
