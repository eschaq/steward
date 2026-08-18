import { Easing, interpolate, useCurrentFrame, useVideoConfig } from 'remotion'
import { loadFont as loadSerif } from '@remotion/google-fonts/SourceSerif4'
import { loadFont as loadSans } from '@remotion/google-fonts/WorkSans'

const { fontFamily: SERIF } = loadSerif()
const { fontFamily: SANS } = loadSans()

export const font = { serif: SERIF, sans: SANS }

/**
 * The tokens `frontend/src/index.css` actually defines, not the RDD's earlier
 * draft palette.
 *
 * That distinction matters here more than anywhere: these cards are intercut
 * with real screen recordings of the app, so a card mixed from the planning
 * doc's #B5674D would sit next to footage of #8e4831 and read as a mistake.
 * DESIGN.md is the authority on visual style and this follows it.
 */
export const color = {
  ink: '#211a14',
  inkDeep: '#17110c',
  onInk: '#f9efe8',
  onInkMuted: 'rgba(249,239,232,0.62)',
  onInkFaint: 'rgba(249,239,232,0.42)',
  inkHairline: 'rgba(249,239,232,0.16)',
  inkAccent: '#ffb59d',
  clay: '#8e4831',
  sage: '#d7e8c8',
  archive: '#efe1cc',
  cream: '#fff8f4',
}

/**
 * Cards sit on Ink, and that is a brand decision rather than a taste one.
 *
 * DESIGN.md reserves the dark surface for *arrival moments* — the sign-in, the
 * estate hero — and the rest of the product stays on warm cream. Title cards
 * bracket the demo the way arriving brackets a visit, and the practical effect
 * is the same: cutting from a dark card into a bright working screen reads as
 * stepping inside.
 */
export const Ink: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    style={{
      width: '100%',
      height: '100%',
      background: color.ink,
      // Barely there. A flat fill reads as a slide; this reads as a surface.
      backgroundImage: `radial-gradient(120% 90% at 22% 12%, rgba(255,181,157,0.10) 0%, rgba(33,26,20,0) 60%)`,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      // The safe area the layout rules ask for, at 1920 scale.
      padding: '140px 200px',
      textAlign: 'center',
    }}
  >
    {children}
  </div>
)

/**
 * Everything fades. Nothing slides, scales, or springs.
 *
 * The brand rules out urgency and gamification, and motion is where that leaks
 * back in first — a card that punches in reads as a pitch. Long, eased
 * cross-fades with a held middle are the visual equivalent of an unhurried
 * voice, and they cut cleanly against the live footage, which has no motion
 * design of its own.
 */
export function useFade({
  inAt = 0,
  inFor = 22,
  outFor = 22,
}: { inAt?: number; inFor?: number; outFor?: number } = {}) {
  const frame = useCurrentFrame()
  const { durationInFrames } = useVideoConfig()
  const ease = Easing.bezier(0.16, 1, 0.3, 1)

  const appear = interpolate(frame, [inAt, inAt + inFor], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: ease,
  })
  const leave = interpolate(
    frame,
    [durationInFrames - outFor, durationInFrames],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease },
  )
  return Math.min(appear, leave)
}

/** A hairline that draws itself, slowly. The one moving element on a card. */
export const Rule: React.FC<{ delay?: number; width?: number; color?: string }> = ({
  delay = 14,
  width = 220,
  color: stroke = color.inkAccent,
}) => {
  const frame = useCurrentFrame()
  return (
    <div
      style={{
        height: 2,
        width,
        background: stroke,
        opacity: 0.85,
        scale: `${interpolate(frame, [delay, delay + 34], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        })} 1`,
      }}
    />
  )
}
