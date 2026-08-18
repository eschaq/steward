# demo-recording

A screen-recording harness for demo footage. **Not part of the app.**

Its own `package.json` and its own `node_modules`, deliberately: Playwright is a
120MB dependency with a browser download behind it, and neither the frontend nor
the backend should carry it to produce a video. Nothing in here is imported by
anything in `frontend/` or `backend/`, and nothing here ships to Cloud Run.

There is already a `frontend/verify.mjs` that drives the real app in Chromium —
that one is a *verification* harness that asserts and reports. This one exists to
produce watchable footage, which turns out to want different things: a viewport
sized to a video frame, typing you can see, and deliberate stillness.

## Setup

```bash
cd demo-recording
npm install
npx playwright install chromium
```

## The smoke test

```bash
node record-smoke.mjs                          # the seeded executor
node record-smoke.mjs someone@example.com pw   # anybody else
```

It signs in to the **live Cloud Run frontend** and lands on the dashboard,
recording at 1920×1080 into `out/`. It is a proof of the pipeline, not a
rehearsal of the demo — the only thing it performs is arriving.

Verified 2026-08-17: 1920×1080 VP8, 25fps, 12.84s, 321 frames, 1.46MB, clean
full decode, and 90 distinct frames after `mpdecimate` — a moving session rather
than a slideshow of two states. Playback checked by extracting stills across the
timeline: sign-in loading, hero loaded, credentials typed, dashboard with 54
belongings.

## Things learned here that the real footage will need

- **The video is finalised on `context.close()`**, not when the script's last
  line runs. `page.video().path()` before that returns a file still being
  written. Take the handle first, close, then rename.
- **Hold still on purpose.** Video is encoded from a screencast stream, so
  frames are emitted when something changes. A script that clicks straight
  through produces a valid file nobody can follow.
- **Viewport and video size must match**, or the page is letterboxed inside the
  frame.
- **`page.type()` with a delay, not `page.fill()`.** Fill sets the value in one
  step; on camera the field simply blinks from empty to full.

## The six demo beats

```bash
node beat1-mediation.mjs      # contested clock, Steward's way through
node beat2-clarify.mjs        # an unplaced photo, answered, reclassified
node beat3-memory.mjs         # a memory posted, Steward asks for another
node beat4-learning.mjs       # four chairs decided, then what it learned
node beat5-marketplace.mjs    # routed to sell: channel, price, draft listing
node beat6-resolve.mjs        # the clock settled on Eban
```

`lib.mjs` holds the rig they share. Masters land in `out/` at 1280x720;
`out/1080p/` carries the lanczos upscales.

**Order matters, and the beats are not idempotent.** Each performs real writes
against the live estate: beat 2 reclassifies the item it clarifies, beat 3's
invitation is once-per-item forever, beat 6 settles the clock that beat 1 shows
contested. Re-shooting means putting that state back first — reverting the
resolution, resetting the item to `needs_clarification`, deleting the thread.

**Two staging facts about Eleanor's House**, both discovered the hard way:

- The executor also belongs to the seeded estate, and arrival picks whichever
  was last chosen. Every beat pins the estate in localStorage before any page
  script runs.
- A disposition can only be recorded on a *resolved* item, and `resolve_item`
  refuses one nobody has claimed. Beats 4 and 5 needed a claim on each chair and
  the lamp before there was any path to the decision they record.

## Two things to sort before shooting the real thing

- ~~**1920 is wider than the app is.**~~ **Settled, and the fix was not the one
  guessed here.** A 1280×720 viewport recorded at 1920×1080 does *not* scale up
  1.5×: Playwright pins the page to the top-left of the larger canvas and greys
  the rest. `recordVideo.size` must equal the viewport. The beats capture 1:1 at
  1280×720 and upscale to 1080p with ffmpeg afterwards, which is where scaling
  belonged anyway.
- **The seeded production items have no photographs.** Every card in the smoke
  recording reads NO PHOTO YET, which is the honest state of the data and a poor
  look on camera. Worth adding photos to the handful of items the demo actually
  visits.

`out/` is gitignored — footage is a build artefact, and these files are large.
