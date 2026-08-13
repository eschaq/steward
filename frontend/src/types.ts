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

export interface Claimant {
  claim_id: string
  user_id: string
  claimant_name: string
  /** So the page can say "You" rather than the reader's own name back at them. */
  is_you: boolean
  comment: string | null
  claimed_at: string
}

export interface ClaimListResponse {
  item_id: string
  /** Documents, duplicates included. */
  count: number
  /** Distinct people — this is what drives the item's status. */
  claimant_count: number
  claims: Claimant[]
}

export interface Message {
  id: string
  item_id: string | null
  user_id: string
  author_name: string
  is_agent: boolean
  text: string
  created_at: string
}

export interface MessageListResponse {
  item_id: string
  count: number
  messages: Message[]
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
/** Plain language, never the raw enum.
 *
 * `unclaimed`/`contested` are the data model's words and they stay in the data
 * model. A family reading their own inventory gets "unspoken for" and "needs a
 * talk" — see the Voice section of docs/estate-agent-branding.md.
 */
export const STATUS_LABEL: Record<ItemStatus, string> = {
  unclaimed: 'Unspoken for',
  claimed: 'Spoken for',
  contested: 'Needs a talk',
  resolved: 'Settled',
  // Not in the branding doc's list — an item already donated, sold, or
  // discarded. Present tense because Disposition starts at `pending` and
  // nothing marks it complete yet.
  routed: 'On its way',
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

/** Statuses where the signed-in member can still put their name forward.
 *
 * `contested` is included on purpose: a third person asking is a real thing that
 * happens, and the claim flow records it rather than blocking it. Everything
 * past that — settled, on its way — is the executor's decision, already made.
 */
export const CLAIMABLE_STATUSES: readonly ItemStatus[] = ['unclaimed', 'contested']

export function isClaimable(status: string): boolean {
  return (CLAIMABLE_STATUSES as readonly string[]).includes(status)
}
