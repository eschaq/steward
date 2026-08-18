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
export const LowerThird: React.FC<{ text: string }> = ({ text }) => {
  const opacity = useFade({ inFor: 24, outFor: 24 })

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'flex-end',
        alignItems: 'flex-start',
        // Clear of the 1080p title-safe area.
        padding: '0 0 132px 128px',
      }}
    >
      <div
        style={{
          opacity,
          display: 'flex',
          alignItems: 'center',
          gap: 26,
          background: 'rgba(23,17,12,0.92)',
          border: `1px solid ${color.inkHairline}`,
          // Row radius from the design system, not a pill: this labels
          // something, and pills are reserved for actions.
          borderRadius: 14,
          padding: '26px 40px 28px',
        }}
      >
        <div
          style={{
            width: 4,
            alignSelf: 'stretch',
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
