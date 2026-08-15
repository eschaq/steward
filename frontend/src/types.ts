/** Shapes the backend returns. Mirrors backend/api.py's response models, which
 * in turn mirror docs/estate-agent-data-model.md. */

/** The statuses an item can be *listed* under — dashboard filters, ledger
 * counts, review-table groups.
 *
 * `removed` is deliberately not here. The API never returns a removed item in
 * any list, so a filter for it would be a chip that is always zero. It is still
 * a real status with a real label — see ALL_ITEM_STATUSES — because the item is
 * still reachable at its own URL and has to say what it is when you get there. */
export const ITEM_STATUSES = [
  'unclaimed',
  'claimed',
  'contested',
  'resolved',
  'routed',
  'needs_clarification',
] as const

/** Every status the backend can send, including the one that is never listed. */
export const ALL_ITEM_STATUSES = [...ITEM_STATUSES, 'removed'] as const

export type ItemStatus = (typeof ITEM_STATUSES)[number]
export type AnyItemStatus = (typeof ALL_ITEM_STATUSES)[number]

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
  /** What the executor actually decided, as against `suggested_disposition`,
   * which is only ever Steward's reading of the photo. Null until decided. */
  decided_channel: string | null
}

/** What a screen reader should say about an item's photograph.
 *
 * The photo is the *only* thing on these screens a non-sighted reader cannot
 * reach, so it carries the two facts the sighted reader gets from it: what the
 * thing is, and what sort of state it's in. Both come from the classifier, and
 * both are already on screen — but a caption below an image is not the image's
 * description, and "item photo" tells nobody anything.
 *
 * Trimmed to one sentence of condition: alt text is announced in one breath,
 * and the full notes sit in the body copy beneath for anyone who wants them.
 */
export function photoAlt(item: {
  ai_category: string
  ai_condition_notes?: string
  ai_est_era_or_brand?: string | null
}): string {
  const era = item.ai_est_era_or_brand?.trim()
  const thing = era ? `${item.ai_category} — ${era}` : item.ai_category
  const first = (item.ai_condition_notes ?? '').split(/(?<=\.)\s+/)[0]?.trim()
  return first ? `Photograph of a ${thing}. ${first}` : `Photograph of a ${thing}.`
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
  /** The item's category when the message is tied to one — so a feed can name
   * what it is talking about instead of showing a document id. */
  item_category: string | null
  text: string
  created_at: string
}

export interface MessageListResponse {
  item_id?: string | null
  estate_id?: string | null
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
export const STATUS_LABEL: Record<AnyItemStatus, string> = {
  unclaimed: 'Unspoken for',
  claimed: 'Spoken for',
  contested: 'Needs a talk',
  resolved: 'Settled',
  // Not in the branding doc's list — an item already donated, sold, or
  // discarded. Present tense because Disposition starts at `pending` and
  // nothing marks it complete yet.
  routed: 'On its way',
  needs_clarification: 'Needs a look',
  // Off the list, not gone. Past tense because it already happened.
  removed: 'Taken off the list',
}

export const STATUS_MEANING: Record<AnyItemStatus, string> = {
  unclaimed: 'Nobody has asked for this one yet.',
  claimed: 'One person has asked for this.',
  contested: 'More than one person has asked for this.',
  resolved: 'The executor has settled who it goes to.',
  routed: 'On its way — donated, sold, or discarded.',
  needs_clarification: "Steward couldn't place this one and has asked about it.",
  removed: "The executor took this one off the list. Nothing about it was thrown away.",
}

/** The first photograph a browser can actually load.
 *
 * `photo_urls` is an array and its first entry is not necessarily displayable —
 * classification records the local file it read (`file:///…`), and an uploaded
 * photo is appended after it. Taking [0] blindly renders "no photo yet" for an
 * item that has one.
 */
export function firstPhoto(urls: string[] | undefined): string | undefined {
  return urls?.find((url) => /^https?:/i.test(url))
}

/** Any status the backend can send, `removed` included — this is the check a
 * chip or a label should use. Filters and groups iterate ITEM_STATUSES instead. */
export function isItemStatus(value: string): value is AnyItemStatus {
  return (ALL_ITEM_STATUSES as readonly string[]).includes(value)
}

export function isListedStatus(value: string): value is ItemStatus {
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

/** The four ways an executor can settle a contested or claimed item, per the
 * data model's Resolution entity. */
export const RESOLUTION_TYPES = [
  'assigned_to_claimant',
  'rotation',
  'outside_appraisal',
  'executor_override',
] as const

export type ResolutionType = (typeof RESOLUTION_TYPES)[number]

/** Written for the executor choosing between them, not as enum glosses. */
export const RESOLUTION_LABEL: Record<ResolutionType, string> = {
  assigned_to_claimant: 'It goes to one of them',
  rotation: 'They share it, in turns',
  outside_appraisal: 'Get it appraised first',
  executor_override: 'Something else — your call',
}

export const RESOLUTION_HELP: Record<ResolutionType, string> = {
  assigned_to_claimant:
    'One person takes it. Whoever steps back usually gets first choice on something of similar meaning.',
  rotation: 'It lives with one household for a while, then the other.',
  outside_appraisal:
    "Nobody can tell what it's worth, and that's part of the difficulty. Decide after.",
  executor_override:
    "Your decision, on whatever grounds. Use this when it isn't going to a claimant.",
}

/** The two that name a person. The backend enforces this too, and additionally
 * requires that person to have actually claimed the item. */
export const NEEDS_RECIPIENT: readonly ResolutionType[] = [
  'assigned_to_claimant',
  'rotation',
]

export function needsRecipient(type: ResolutionType): boolean {
  return NEEDS_RECIPIENT.includes(type)
}

export interface Me {
  estate_id: string
  user_id: string
  role: 'executor' | 'beneficiary' | null
  accepted: boolean
  /** The estate's own name. Null if the record has none — say something general
   * rather than printing a document id at a grieving family. */
  estate_name: string | null
  /** An invite here is waiting to be accepted. */
  invite_pending: boolean
}

export interface Membership {
  estate_id: string
  user_id: string
  role: 'executor' | 'beneficiary'
  accepted: boolean
  /** True only when this call is what turned a pending invite into a
   * membership — the one moment someone is genuinely new here. */
  first_accept: boolean
  /** Whether the invitation email actually went out. A courtesy reported on top
   * of the membership — an invite that couldn't be emailed is still an invite. */
  invite_email_sent: boolean
  invite_email_note: string | null
}

export interface Member {
  user_id: string
  display_name: string
  email: string
  role: 'executor' | 'beneficiary'
  accepted: boolean
  invited_at: string
  accepted_at: string | null
  is_you: boolean
}

export interface MemberListResponse {
  estate_id: string
  count: number
  pending_count: number
  members: Member[]
}

export const ROLE_LABEL: Record<string, string> = {
  executor: 'Executor',
  beneficiary: 'Family',
}

export const ROLE_HELP: Record<string, string> = {
  executor: 'Records how contested pieces are settled, and where everything ends up.',
  beneficiary: 'Can look through the estate and ask for the things that matter to them.',
}

export interface ResolutionDetail {
  resolution_id: string
  item_id: string
  resolution_type: string
  resolved_by_user_id: string
  resolved_by_name: string
  resolved_to_user_id: string | null
  resolved_to_name: string | null
  notes: string
  resolved_at: string
}

export interface ReviewRow {
  id: string
  ai_category: string
  ai_est_era_or_brand: string | null
  ai_classification_confidence: number
  suggested_disposition: string
  status: string
  claimant_count: number
  /** First photograph, if the item has one — so the table can show a thumbnail
   * without a second request per row. */
  photo_url: string | null
  /** Set only when exactly one person asked — the case the table can settle
   * in one click without hiding anything from the executor. */
  sole_claimant_id: string | null
  sole_claimant_name: string | null
  decided_type: string | null
  decided_to_name: string | null
  decided_notes: string | null
  /** Where the piece is headed, once the executor has said. Null means nobody
   * has decided yet — for a settled item that is a prompt, not an absence. */
  disposition: DispositionDetail | null
}

export interface ReviewResponse {
  estate_id: string
  count: number
  rows: ReviewRow[]
}

/** The order an executor works in: what needs a decision, then what is waiting,
 * then what is done. Not alphabetical, not the enum's own order. */
export const REVIEW_ORDER: readonly ItemStatus[] = [
  'contested',
  'claimed',
  'needs_clarification',
  'unclaimed',
  'resolved',
  'routed',
]

/** The three channels an executor can choose in the UI. `sell_auction_bulk` is
 * Tier 3 and has no path to it — see the data model doc. */
export const DISPOSITION_CHOICES = ['donate', 'sell', 'discard'] as const
export type DispositionChoice = (typeof DISPOSITION_CHOICES)[number]

export const DISPOSITION_LABEL: Record<DispositionChoice, string> = {
  donate: 'Give it away',
  sell: 'Sell it',
  discard: 'Let it go',
}

export const DISPOSITION_HELP: Record<DispositionChoice, string> = {
  donate: 'To a charity shop, or to someone who will use it.',
  sell: "Steward will suggest where to list it, and why that's the right place.",
  discard: "It has come to the end of its life and isn't worth passing on.",
}

/** What the stored channel is called when read back. `sell` becomes
 * `sell_marketplace` at the Disposition seam. */
/** The same four destinations, short enough for a table cell. `whereItGoes()`
 * is what screens should call — it folds in the marketplace platform, so a sold
 * piece names where rather than just saying it is being sold. */
export const CHANNEL_SHORT: Record<string, string> = {
  donate: 'Given away',
  discard: 'Let go',
  sell_marketplace: 'Sold',
  sell_auction_bulk: 'Auction',
}

export function whereItGoes(disposition: DispositionDetail | null): string | null {
  if (!disposition) return null
  const short = CHANNEL_SHORT[disposition.channel] ?? disposition.channel
  const platform = disposition.listing?.platform
  if (disposition.channel === 'sell_marketplace' && platform) {
    return `Sold via ${PLATFORM_LABEL[platform] ?? platform}`
  }
  return short
}

export const CHANNEL_LABEL: Record<string, string> = {
  donate: 'Being given away',
  discard: 'Being let go',
  sell_marketplace: 'Being sold',
  sell_auction_bulk: 'Going to auction',
}

export const PLATFORM_LABEL: Record<string, string> = {
  vinted: 'Vinted',
  fb_marketplace: 'Facebook Marketplace',
  ebay: 'eBay',
  poshmark: 'Poshmark',
  other: 'Somewhere else',
}

export interface ListingDetail {
  listing_id: string
  disposition_id: string
  platform: string
  platform_recommendation_reason: string
  suggested_price: number | null
  listing_draft_title: string | null
  listing_draft_description: string | null
  listing_url: string | null
  listing_status: string
}

export interface DispositionDetail {
  disposition_id: string
  item_id: string
  channel: string
  status: string
  completed_at: string | null
  listing: ListingDetail | null
}
