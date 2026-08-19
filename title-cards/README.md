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

**Lower-thirds sit at the top of frame, not the bottom.** The plate is opaque,
so it always covers something; the only question is what. Bottom-left put it
squarely on the mediation message — the payoff of the very beat it was
labelling — which the composite test caught. At the top it clears the app's
content column at the moments that matter. It still covers *something* (a
claimant's quote at one timestamp, card description text at another), so place
these against a part of the take where the upper band is chrome or whitespace.

**Durations are generous on purpose.** An editor can always trim, and cannot
invent frames that were never rendered.
