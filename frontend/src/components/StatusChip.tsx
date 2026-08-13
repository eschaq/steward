import { STATUS_LABEL, STATUS_MEANING, isItemStatus } from '../types'

/** The status of one item, as an archival tag.
 *
 * Rectangular and barely rounded on purpose — a tag tied to an object, not a
 * pill. Tonal fills stay desaturated so the inventory never reads as alarming.
 *
 * A status the backend sends but this UI doesn't recognise is shown as itself
 * rather than swallowed — a silently dropped state is worse than an odd-looking
 * tag.
 */
export function StatusChip({ status }: { status: string }) {
  const known = isItemStatus(status)
  return (
    <span
      className={`tag tag--${known ? status : 'unclaimed'}`}
      title={known ? STATUS_MEANING[status] : `Unrecognised status: ${status}`}
    >
      {known ? STATUS_LABEL[status] : status}
    </span>
  )
}
