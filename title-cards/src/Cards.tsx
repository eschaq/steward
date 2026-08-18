import { AbsoluteFill } from 'remotion'

import { Ink, Rule, color, font, useFade } from './brand'

/** Full-frame cards. One message each — the layout rules' point that a frame
 * with one strong message beats a frame full of widgets, and the brand's point
 * that nothing here should feel busy. */

export const Opening: React.FC = () => {
  const opacity = useFade({ inFor: 30, outFor: 26 })
  return (
    <AbsoluteFill>
      <Ink>
        <div style={{ opacity, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 40 }}>
          <h1
            style={{
              fontFamily: font.serif,
              fontWeight: 600,
              fontSize: 190,
              lineHeight: 1,
              letterSpacing: '-0.03em',
              color: color.onInk,
              margin: 0,
            }}
          >
            Steward
          </h1>
          <Rule delay={22} width={260} />
          <p
            style={{
              fontFamily: font.sans,
              fontSize: 54,
              lineHeight: 1.45,
              color: color.onInkMuted,
              margin: 0,
              maxWidth: 1200,
            }}
          >
            Decide together. Steward it well.
          </p>
        </div>
      </Ink>
    </AbsoluteFill>
  )
}

export const Problem: React.FC = () => {
  const opacity = useFade({ inFor: 26, outFor: 26 })
  return (
    <AbsoluteFill>
      <Ink>
        <h2
          style={{
            opacity,
            fontFamily: font.serif,
            fontWeight: 600,
            fontSize: 104,
            lineHeight: 1.22,
            letterSpacing: '-0.02em',
            color: color.onInk,
            margin: 0,
            maxWidth: 1440,
          }}
        >
          The paperwork gets handled.
          <br />
          <span style={{ color: color.inkAccent }}>The belongings don't.</span>
        </h2>
      </Ink>
    </AbsoluteFill>
  )
}

export const Positioning: React.FC = () => {
  const opacity = useFade({ inFor: 28, outFor: 28 })
  return (
    <AbsoluteFill>
      <Ink>
        <div
          style={{
            opacity,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 44,
            maxWidth: 1480,
          }}
        >
          <p
            style={{
              fontFamily: font.sans,
              fontSize: 52,
              lineHeight: 1.5,
              color: color.onInkMuted,
              margin: 0,
            }}
          >
            General AI mediators resolve what you tell them.
          </p>
          <Rule delay={26} width={200} />
          <p
            style={{
              fontFamily: font.serif,
              fontWeight: 600,
              fontSize: 82,
              lineHeight: 1.28,
              letterSpacing: '-0.015em',
              color: color.onInk,
              margin: 0,
            }}
          >
            Steward mediates what actually happened in a real claim ledger.
          </p>
        </div>
      </Ink>
    </AbsoluteFill>
  )
}

/** The stack, set as one line of small caps rather than a row of logos —
 * badges and pills are the web-UI pattern the layout rules warn against, and
 * the brand's chips are archival tags, not marketing. */
export const Stack: React.FC = () => {
  const opacity = useFade({ inFor: 26, outFor: 26 })
  // Two deliberate rows rather than one wrapping line. Letting flex wrap put a
  // separator at the end of a line — "Google ADK ·" then a break — which reads
  // as a typo. Grouping fixes where the break falls and keeps every row ending
  // on a word.
  const rows = [
    ['Gemini 3.5 via Vertex AI', 'Google ADK'],
    ['Cloud Run', 'Firestore'],
  ]
  return (
    <AbsoluteFill>
      <Ink>
        <div
          style={{
            opacity,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 46,
          }}
        >
          <span
            style={{
              fontFamily: font.sans,
              fontSize: 26,
              fontWeight: 600,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              color: color.onInkFaint,
            }}
          >
            Built on
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 26 }}>
            {rows.map((row) => (
              <div
                key={row.join()}
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 30 }}
              >
                {row.map((part, i) => (
                  <div key={part} style={{ display: 'flex', alignItems: 'center', gap: 30 }}>
                    <span
                      style={{
                        fontFamily: font.serif,
                        fontWeight: 600,
                        fontSize: 62,
                        color: color.onInk,
                        lineHeight: 1.2,
                      }}
                    >
                      {part}
                    </span>
                    {i < row.length - 1 && (
                      <span style={{ fontSize: 40, color: color.inkAccent, lineHeight: 1 }}>·</span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </Ink>
    </AbsoluteFill>
  )
}

export const Closing: React.FC = () => {
  const opacity = useFade({ inFor: 30, outFor: 34 })
  return (
    <AbsoluteFill>
      <Ink>
        <div
          style={{
            opacity,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 40,
          }}
        >
          <h2
            style={{
              fontFamily: font.serif,
              fontWeight: 600,
              fontSize: 86,
              lineHeight: 1.24,
              letterSpacing: '-0.015em',
              color: color.onInk,
              margin: 0,
              maxWidth: 1400,
            }}
          >
            Built on Gemini 3.5 and Google Cloud
          </h2>
          <Rule delay={24} width={220} />
          <p
            style={{
              fontFamily: font.sans,
              fontSize: 46,
              color: color.onInkMuted,
              margin: 0,
            }}
          >
            github.com/eschaq/steward
          </p>
          <p
            style={{
              fontFamily: font.sans,
              fontSize: 34,
              fontWeight: 500,
              letterSpacing: '0.04em',
              color: color.inkAccent,
              margin: 0,
            }}
          >
            #AllThingsAgenticHackathon
          </p>
        </div>
      </Ink>
    </AbsoluteFill>
  )
}
