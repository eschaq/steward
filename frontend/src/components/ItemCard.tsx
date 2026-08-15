import { Link } from 'react-router-dom'

import { CHANNEL_SHORT, firstPhoto, photoAlt, type Item } from '../types'
import { StatusChip } from './StatusChip'

function titleCase(value: string): string {
  return value.replace(/\b[a-z]/g, (c) => c.toUpperCase())
}

/** One belonging, laid out like a museum placard: photo, serif title, archival
 * tags, then the notes.
 *
 * The whole card is the link to the item's own page — a target the size of the
 * card, not a small "view" affordance tucked in a corner.
 */
export function ItemCard({ item }: { item: Item }) {
  const photo = firstPhoto(item.photo_urls)
  const usable = Boolean(photo)

  // The data model gives an item no name, so the category is the name — and the
  // era or brand is provenance, not a title. Using the era as the heading reads
  // fine for "Louis XV style" and badly for "signed, dated 1962" or "unmarked
  // seal, studio piece", which are qualifiers rather than things.
  const title = titleCase(item.ai_category)
  const era = item.ai_est_era_or_brand?.trim()

  return (
    <Link to={`/items/${item.id}`} className="card">
      <div className={`card__photo${usable ? '' : ' card__photo--empty'}`}>
        {usable ? (
          <img src={photo} alt={photoAlt(item)} loading="lazy" />
        ) : (
          <span>No photo yet</span>
        )}
        <span className="card__chip">
          <StatusChip status={item.status} />
        </span>
      </div>

      <div className="card__body">
        {era && (
          <div className="card__marks">
            <span className="tag tag--routed">{era}</span>
          </div>
        )}

        <h2 className="card__title">{title}</h2>
        <p className="card__notes">{item.ai_condition_notes}</p>

        <div className="card__foot">
          {/* Once the executor has decided, their decision is the fact — the
              suggestion it replaced is history and stops being shown. */}
          <span>
            {item.decided_channel
              ? CHANNEL_SHORT[item.decided_channel] ?? item.decided_channel
              : item.suggested_disposition === 'uncertain'
                ? 'No suggestion yet'
                : `Leaning ${item.suggested_disposition}`}
          </span>
          <span>{Math.round(item.ai_classification_confidence * 100)}% sure</span>
        </div>
      </div>
    </Link>
  )
}
