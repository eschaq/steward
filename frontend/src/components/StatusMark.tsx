/** A small drawn mark for each status, so the six are told apart by shape as
 * well as by hue.
 *
 * WCAG 1.4.1: colour must never be the only carrier of meaning. The tag already
 * has its label in words, which satisfies that on its own — this is for the
 * dashboard scan, where six tonal chips read as a wash of similar warm colours
 * to anyone with a red-green deficiency, and the eye is matching shapes long
 * before it reads any of them.
 *
 * Drawn, not an icon set: one stroke weight, all on a 12px square, no fills, no
 * corner flourishes. A pencil mark in a ledger margin — the archival annotation
 * the tag is already pretending to be. Nothing here is a warning triangle.
 *
 * `aria-hidden` throughout: the word beside it already says this.
 */
export function StatusMark({ status }: { status: string }) {
  const common = {
    className: 'status-mark',
    viewBox: '0 0 12 12',
    width: 12,
    height: 12,
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.4,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    focusable: false,
  }

  switch (status) {
    // Unspoken for — an empty ring. Nobody's mark on it yet.
    case 'unclaimed':
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="4" />
        </svg>
      )
    // Spoken for — one name on it, so the ring is filled in.
    case 'claimed':
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="4" fill="currentColor" stroke="none" />
        </svg>
      )
    // Needs a talk — two marks, side by side and overlapping. Two people, not
    // a collision: no cross, no exclamation.
    case 'contested':
      return (
        <svg {...common}>
          <circle cx="4.3" cy="6" r="3.1" />
          <circle cx="7.7" cy="6" r="3.1" />
        </svg>
      )
    // Settled — a tick, the way you'd tick a line on a list.
    case 'resolved':
      return (
        <svg {...common}>
          <path d="M1.8 6.4 L4.6 9.2 L10.2 2.8" />
        </svg>
      )
    // On its way — an arrow leaving.
    case 'routed':
      return (
        <svg {...common}>
          <path d="M1.6 6h8.4" />
          <path d="M7.2 3.2 10 6l-2.8 2.8" />
        </svg>
      )
    // Needs a look — a question, asked quietly.
    case 'needs_clarification':
      return (
        <svg {...common}>
          <path d="M4.1 4.1a1.95 1.95 0 1 1 2.6 1.84c-.42.16-.7.56-.7 1.01v.4" />
          <path d="M6 9.7v.1" />
        </svg>
      )
    // An unrecognised status still gets a mark, so the row doesn't jump.
    default:
      return (
        <svg {...common}>
          <path d="M2.6 6h6.8" />
        </svg>
      )
  }
}
