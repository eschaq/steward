import type { Item } from '../types'
import { StatusChip } from './StatusChip'

/** One belonging, laid out like a card in a family album.
 *
 * Serif title, category above it, condition notes below. Not a detail view —
 * that screen isn't built yet, so nothing here pretends to be clickable.
 */
function titleCase(value: string): string {
  return value.replace(/\b[a-z]/g, (c) => c.toUpperCase())
}

export function ItemCard({ item }: { item: Item }) {
  const photo = item.photo_urls?.[0]
  const usable = Boolean(photo && /^https?:/.test(photo))

  // The data model gives an item no name — only a category and, sometimes, an
  // estimated era or brand. The era makes the better heading when there is one
  // ("French Provincial style"); otherwise the category is all we have, and
  // printing it as both eyebrow and heading just says the same word twice.
  const title = item.ai_est_era_or_brand?.trim() || titleCase(item.ai_category)
  const showCategory = title.toLowerCase() !== item.ai_category.trim().toLowerCase()

  return (
    <article className="card">
      <div className={`card__photo${usable ? '' : ' card__photo--empty'}`}>
        {usable ? (
          <img src={photo} alt={item.ai_category} loading="lazy" />
        ) : (
          <span className="label-sm">No photo yet</span>
        )}
        <span className="card__chip">
          <StatusChip status={item.status} />
        </span>
      </div>

      <div className="card__body">
        {showCategory && <span className="card__category">{item.ai_category}</span>}
        <h3 className="card__title">{title}</h3>
        <p className="card__notes body-md">{item.ai_condition_notes}</p>

        <div className="card__foot">
          <span>
            {item.suggested_disposition === 'uncertain'
              ? 'No suggestion yet'
              : `Suggested: ${item.suggested_disposition}`}
          </span>
          <span>{Math.round(item.ai_classification_confidence * 100)}% sure</span>
        </div>
      </div>
    </article>
  )
}
