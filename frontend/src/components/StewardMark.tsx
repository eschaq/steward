/** The Steward mark: a gable, a door, a chimney, and a thread beneath.
 *
 * Drawn from the logo brief in docs/estate-agent-branding.md — "a simple
 * line-drawn house... warm terracotta line on cream, with a small human touch...
 * a subtle thread connecting shapes." The thread is the last element to survive
 * scaling down, so it's dropped below ~28px rather than turning into a smudge.
 */
export function StewardMark({
  size = 28,
  color = 'currentColor',
  thread,
}: {
  size?: number
  color?: string
  /** Defaults to on at 28px and above. */
  thread?: boolean
}) {
  const showThread = thread ?? size >= 28
  // Heavier stroke at small sizes, so the mark holds together in an app bar.
  const stroke = size < 24 ? 3.8 : size < 32 ? 3.4 : 3

  return (
    <svg
      width={size}
      height={size * (52 / 60)}
      viewBox="0 0 60 52"
      fill="none"
      role="img"
      aria-label="Steward"
    >
      <g
        stroke={color}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M5 25 L30 6 L55 25" />
        <path d="M12 21 V44 H48 V21" />
        <path d="M25 44 V32 H35 V44" />
        {size >= 24 && <path d="M43 15 V9 H48 V19" />}
      </g>
      {showThread && (
        <path
          d="M3 49 C18 44, 42 44, 57 49"
          stroke={color}
          strokeWidth={2.2}
          strokeLinecap="round"
          opacity={0.45}
          fill="none"
        />
      )}
    </svg>
  )
}

/** Mark plus wordmark, the way it appears in the app bar and on sign-in. */
export function StewardLockup({
  size = 28,
  color = 'currentColor',
  className,
}: {
  size?: number
  color?: string
  className?: string
}) {
  return (
    <span className={`lockup${className ? ` ${className}` : ''}`}>
      <StewardMark size={size} color={color} />
      <span className="lockup__name" style={{ fontSize: size * 0.76 }}>
        Steward
      </span>
    </span>
  )
}
