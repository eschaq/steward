import { AbsoluteFill } from 'remotion'

import { color, font, useFade } from './brand'

/**
 * A label that sits over live footage, and gets out of the way.
 *
 * **Rendered on transparency, not on a card.** These overlay the Playwright
 * recordings, so they go out as ProRes 4444 with an alpha channel — see the
 * render script. Nothing here may paint a full-frame background, which is why
 * the `AbsoluteFill` carries no colour of its own.
 *
 * Understated on purpose. The app's own chrome is warm cream and the footage is
 * busy with real text, so the label is a single dark plate with a clay edge,
 * placed low-left where the app's content column is thinnest. No box shadow —
 * the brand has none anywhere, and depth here is the plate's own tone against
 * whatever is behind it.
 */
/** The band's height, and the single number an editor needs: the footage is
 * scaled to fit the 1080 - BAND_HEIGHT that remains, so nothing it shows ever
 * passes underneath the label. */
export const BAND_HEIGHT = 150

export const LowerThird: React.FC<{ text: string }> = ({ text }) => {
  const opacity = useFade({ inFor: 24, outFor: 24 })

  return (
    <AbsoluteFill
      style={{
        // **A band across the top, not a plate floating over the picture.**
        //
        // A floating plate is opaque, so it always covers something. Measured on
        // the beat-1 frame it was meant to label: the tallest horizontal strip
        // of that screen carrying no content at all is 37px at 720p, and the
        // label needs 112px. There is nowhere to put it that is clear of
        // content, so the answer is to make room rather than to keep hunting for
        // it — the footage sits *below* this band, and the label covers nothing.
        //
        // See README for the one transform an editor applies to the footage.
        justifyContent: 'flex-start',
        alignItems: 'flex-start',
        padding: 0,
      }}
    >
      <div
        style={{
          opacity,
          // The band itself: full width, fixed height, so the footage below it
          // always begins at exactly the same line.
          width: '100%',
          height: BAND_HEIGHT,
          display: 'flex',
          alignItems: 'center',
          gap: 26,
          padding: '0 128px',
          background: color.inkDeep,
          borderBottom: `1px solid ${color.inkHairline}`,
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            width: 4,
            height: 54,
            background: color.inkAccent,
            borderRadius: 2,
          }}
        />
        <span
          style={{
            fontFamily: font.serif,
            fontWeight: 600,
            fontSize: 46,
            lineHeight: 1.25,
            letterSpacing: '-0.01em',
            color: color.onInk,
          }}
        >
          {text}
        </span>
      </div>
    </AbsoluteFill>
  )
}

/** The six, in the order the demo plays them. */
export const LOWER_THIRDS = [
  { id: 'lt1-two-people', text: 'The moment two people want the same thing' },
  { id: 'lt2-asks-answers', text: 'The agent asks. The family answers.' },
  { id: 'lt3-nobody-else', text: 'Nobody else does this part' },
  { id: 'lt4-learned', text: 'What Steward has learned' },
  { id: 'lt5-honest', text: "Honest, even when it's for sale" },
  { id: 'lt6-full-circle', text: 'Full circle' },
] as const
