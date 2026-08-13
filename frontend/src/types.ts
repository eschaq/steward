/** Shapes the backend returns. Mirrors backend/api.py's response models, which
 * in turn mirror docs/estate-agent-data-model.md. */

export const ITEM_STATUSES = [
  'unclaimed',
  'claimed',
  'contested',
  'resolved',
  'routed',
  'needs_clarification',
] as const

export type ItemStatus = (typeof ITEM_STATUSES)[number]

export interface Item {
  id: string
  estate_id: string
  ai_category: string
  ai_condition_notes: string
  ai_est_era_or_brand: string | null
  ai_classification_confidence: number
  suggested_disposition: string
  status: string
  photo_urls: string[]
}

export interface ItemListResponse {
  estate_id: string
  count: number
  items: Item[]
}

/** How each status is named and described for the family.
 *
 * All six live here, including the three the Stitch mockup's filter tabs left
 * out. A status the data model can produce but the UI can't show is a state the
 * family would never find out about. */
export const STATUS_LABEL: Record<ItemStatus, string> = {
  unclaimed: 'Unclaimed',
  claimed: 'Claimed',
  contested: 'Contested',
  resolved: 'Resolved',
  routed: 'Routed',
  needs_clarification: 'Needs a look',
}

export const STATUS_MEANING: Record<ItemStatus, string> = {
  unclaimed: 'Nobody has asked for this one yet.',
  claimed: 'One person has asked for this.',
  contested: 'More than one person has asked for this.',
  resolved: 'The executor has settled who it goes to.',
  routed: 'On its way — donated, sold, or discarded.',
  needs_clarification: "Steward couldn't place this one and has asked about it.",
}

export function isItemStatus(value: string): value is ItemStatus {
  return (ITEM_STATUSES as readonly string[]).includes(value)
}
