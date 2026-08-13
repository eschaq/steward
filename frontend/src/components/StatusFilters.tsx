import { ITEM_STATUSES, STATUS_LABEL, STATUS_MEANING, type ItemStatus } from '../types'

export type Filter = ItemStatus | 'all'

/** All six statuses, always — plus "Everything".
 *
 * The Stitch mockup showed three tabs (unclaimed, claimed, contested). The data
 * model has six, and an item can genuinely be resolved, routed, or waiting on a
 * clarifying question. A tab with a zero count is honest; a missing tab hides a
 * state the family's items can actually be in.
 */
export function StatusFilters({
  active,
  counts,
  total,
  onChange,
}: {
  active: Filter
  counts: Record<ItemStatus, number>
  total: number
  onChange: (next: Filter) => void
}) {
  return (
    <div className="filters" role="group" aria-label="Filter by status">
      <button
        type="button"
        className={`filter${active === 'all' ? ' filter--on' : ''}`}
        aria-pressed={active === 'all'}
        onClick={() => onChange('all')}
      >
        Everything <span className="filter__count">{total}</span>
      </button>

      {ITEM_STATUSES.map((status) => {
        const count = counts[status]
        return (
          <button
            key={status}
            type="button"
            title={STATUS_MEANING[status]}
            className={
              `filter${active === status ? ' filter--on' : ''}` +
              (count === 0 ? ' filter--empty' : '')
            }
            aria-pressed={active === status}
            onClick={() => onChange(status)}
          >
            {STATUS_LABEL[status]} <span className="filter__count">{count}</span>
          </button>
        )
      })}
    </div>
  )
}
