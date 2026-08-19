# title-cards

Remotion project for the demo video's title cards and lower-thirds. **Not part
of the app** — its own package, imported by nothing, shipped nowhere.

```bash
npm install
npm run dev        # Remotion Studio, to preview and tweak
./render.sh        # every card into out/
```

## What comes out, and in which format

`out/` holds two kinds of file, and the difference is not cosmetic:

| | Format | Why |
| --- | --- | --- |
| Full-frame cards | H.264 MP4 | opaque; DaVinci takes them without ceremony |
| Six lower-thirds | **ProRes 4444 .mov** | they overlay live footage and need a real **alpha channel** |

H.264 has no alpha. A "transparent" MP4 would arrive in the timeline as a black
box sitting on the recording, so the lower-thirds are rendered
`--codec=prores --prores-profile=4444 --pixel-format=yuva444p10le`. They are
~15MB each against ~400KB for a card; that is the alpha, and it is the point.

Verified by compositing one over a real frame of `beat1-mediation.webm` with
ffmpeg — the app shows through around the plate.

## Design notes

**Palette from `frontend/src/index.css`, not from the RDD's draft.** These cards
are intercut with screen recordings of the running app, so a card mixed from the
planning doc's `#B5674D` would sit next to footage of `#8e4831` and read as a
mistake. DESIGN.md is the authority; `src/brand.tsx` mirrors its tokens.

**Cards sit on Ink.** DESIGN.md reserves the dark surface for arrival moments —
sign-in, the estate hero — while the working screens stay warm cream. Title
cards bracket the demo the way arriving brackets a visit, and cutting from a
dark card into a bright working screen reads as stepping inside.

**Everything fades; nothing slides, scales or springs.** The brand rules out
urgency, and motion is where that leaks back in first — a card that punches in
reads as a pitch. The only moving element is a hairline rule that draws itself.

**Lower-thirds are a band across the top, and the footage sits below them.**

A floating plate is opaque, so it covers something wherever it goes. Bottom-left
put it on the mediation message — the payoff of the beat it was labelling — and
moving it up only traded that for a claimant's quote. So this was measured
rather than argued: on that frame, **the tallest horizontal strip carrying no
content at all is 37px** at 720p, and the label needs 112px. There is nowhere
clear to put it.

The band makes the room instead. It occupies **y=0–149** and everything below is
transparent (verified on the rendered alpha channel), so the label covers nothing
at all — provided the footage is placed under it:

| In DaVinci, on the footage clip | Value |
| --- | --- |
| Zoom | **0.861** (930 ÷ 1080) |
| Position Y | **+75** (down half the band) |
| Background behind it | `#fff8f4`, the app's own cream |

That is one transform, applied once and copied to every clip the labels sit
over. `BAND_HEIGHT` in `src/LowerThird.tsx` is the single number both sides
derive from; change it there and recompute the zoom.

Proof is `out/v-overlay.jpg` — the same beat-1 frame with the band applied,
showing both claim quotes and every line of Steward's mediation.

**Durations are generous on purpose.** An editor can always trim, and cannot
invent frames that were never rendered.
