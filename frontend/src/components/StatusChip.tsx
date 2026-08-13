import { STATUS_LABEL, STATUS_MEANING, isItemStatus } from '../types'

/** The status of one item, in the muted palette.
 *
 * A status the backend sends but this UI doesn't recognise is shown as itself
 * rather than swallowed — a silently dropped state is worse than an odd-looking
 * chip.
 */
export function StatusChip({ status }: { status: string }) {
  const known = isItemStatus(status)
  return (
    <span
      className={`chip chip--${known ? status : 'unclaimed'}`}
      title={known ? STATUS_MEANING[status] : `Unrecognised status: ${status}`}
    >
      {known ? STATUS_LABEL[status] : status}
    </span>
  )
}
