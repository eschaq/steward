import { STATUS_LABEL, STATUS_MEANING, isItemStatus } from '../types'
import { StatusMark } from './StatusMark'

/** The status of one item, as an archival tag.
 *
 * Rectangular and barely rounded on purpose — a tag tied to an object, not a
 * pill. Tonal fills stay desaturated so the inventory never reads as alarming.
 *
 * A status the backend sends but this UI doesn't recognise is shown as itself
 * rather than swallowed — a silently dropped state is worse than an odd-looking
 * tag.
 *
 * The drawn mark carries the same distinction as the fill colour, so the six
 * are separable without hue (WCAG 1.4.1). It is aria-hidden — the label beside
 * it already says the thing.
 */
export function StatusChip({ status }: { status: string }) {
  const known = isItemStatus(status)
  return (
    <span
      className={`tag tag--${known ? status : 'unclaimed'}`}
      title={known ? STATUS_MEANING[status] : `Unrecognised status: ${status}`}
    >
      <StatusMark status={status} />
      {known ? STATUS_LABEL[status] : status}
    </span>
  )
}
