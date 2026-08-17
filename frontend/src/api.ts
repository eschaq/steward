/** Calls to the backend API, with the caller's ID token attached.
 *
 * getIdToken() returns the cached token and refreshes it when it's close to
 * expiring, so this asks for it per request rather than holding one that will
 * quietly go stale after an hour.
 */

import { auth, API_BASE_URL } from './firebase'
import type {
  ClarifyResponse,
  ClaimListResponse,
  Item,
  ItemListResponse,
  Me,
  MemberListResponse,
  Membership,
  Message,
  MessageListResponse,
  DispositionChoice,
  DispositionDetail,
  ListingDetail,
  ResolutionDetail,
  ResolutionType,
  ReviewResponse,
} from './types'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** Structured `detail` when the server sent an object rather than a string
     * — the photo pre-check uses this to hand the UI a concern it can act on. */
    readonly detail?: unknown,
  ) {
    super(message)
  }
}

/** The photo pre-check's verdict, when an upload came back 422 because the
 * picture looked unusable. */
export interface PhotoConcern {
  kind: 'photo_concern'
  problem: string
  message: string
}

export function photoConcern(error: unknown): PhotoConcern | null {
  if (!(error instanceof ApiError) || error.status !== 422) return null
  const d = error.detail as PhotoConcern | undefined
  return d && d.kind === 'photo_concern' ? d : null
}

async function authorizedFetch(
  path: string,
  init?: { method?: string; body?: unknown; form?: FormData },
): Promise<Response> {
  const user = auth.currentUser
  if (!user) throw new ApiError(401, 'You are signed out. Sign in again to continue.')

  const token = await user.getIdToken()

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: init?.method ?? 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
        // No Content-Type for FormData — the browser sets it, and must, because
        // it has to include the multipart boundary.
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: init?.form ?? (init?.body ? JSON.stringify(init.body) : undefined),
    })
  } catch {
    // fetch() throws the same TypeError for a dead server and for a CORS
    // rejection, so this cannot say which — and asserting one would send
    // someone looking in the wrong place. Both are named, most likely first.
    const sameHost =
      typeof window !== 'undefined' && API_BASE_URL.includes(window.location.hostname)
    throw new ApiError(
      0,
      `Couldn't reach the backend at ${API_BASE_URL}. Either it isn't running ` +
        '(cd backend && .venv/bin/uvicorn api:app --reload), or it is running ' +
        'but refused this origin' +
        (sameHost ? '' : ' — it is on a different host from this page') +
        `. For the second, start it with STEWARD_ALLOWED_ORIGINS including ${
          typeof window !== 'undefined' ? window.location.origin : 'this origin'
        }.`,
    )
  }

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body) => body?.detail)
      .catch(() => null)
    // FastAPI's `detail` is a string for most errors and an object for the
    // photo pre-check; keep both rather than stringifying the useful one.
    const text =
      typeof detail === 'string'
        ? detail
        : (detail as { message?: string })?.message ??
          `Request failed (${response.status}).`
    throw new ApiError(response.status, text, detail)
  }

  return response
}

export async function fetchEstateItems(estateId: string): Promise<ItemListResponse> {
  const response = await authorizedFetch(`/estates/${encodeURIComponent(estateId)}/items`)
  return (await response.json()) as ItemListResponse
}

export async function fetchItem(itemId: string): Promise<Item> {
  const response = await authorizedFetch(`/items/${encodeURIComponent(itemId)}`)
  return (await response.json()) as Item
}

export async function fetchItemMessages(itemId: string): Promise<MessageListResponse> {
  const response = await authorizedFetch(`/items/${encodeURIComponent(itemId)}/messages`)
  return (await response.json()) as MessageListResponse
}

export async function fetchItemClaims(itemId: string): Promise<ClaimListResponse> {
  const response = await authorizedFetch(`/items/${encodeURIComponent(itemId)}/claims`)
  return (await response.json()) as ClaimListResponse
}

/** Put the signed-in member's name forward. The claimant is the caller — there
 * is no user id in the body to forge. */
export async function claimItem(itemId: string, comment?: string): Promise<void> {
  await authorizedFetch(`/items/${encodeURIComponent(itemId)}/claim`, {
    method: 'POST',
    body: { comment: comment?.trim() || null },
  })
}

export async function fetchEstateMessages(estateId: string): Promise<MessageListResponse> {
  const response = await authorizedFetch(
    `/estates/${encodeURIComponent(estateId)}/messages`,
  )
  return (await response.json()) as MessageListResponse
}

/** Post to the estate's feed. The author is the caller — there is no user id in
 * the body, so nobody can post as somebody else, or as Steward. */
export async function postEstateMessage(
  estateId: string,
  text: string,
  itemId?: string,
): Promise<Message> {
  const response = await authorizedFetch(`/estates/${encodeURIComponent(estateId)}/messages`, {
    method: 'POST',
    body: { text, item_id: itemId ?? null },
  })
  return (await response.json()) as Message
}

/** What the caller is on this estate — used to decide what to offer, never as
 * the authorization itself. Every write is still checked server-side. */
export async function fetchMe(estateId: string): Promise<Me> {
  const response = await authorizedFetch(`/estates/${encodeURIComponent(estateId)}/me`)
  return (await response.json()) as Me
}

export async function fetchMembers(estateId: string): Promise<MemberListResponse> {
  const response = await authorizedFetch(`/estates/${encodeURIComponent(estateId)}/members`)
  return (await response.json()) as MemberListResponse
}

/** Invite someone to the estate.
 *
 * `create_account` is always true from here: a membership row has to point at a
 * Firebase Auth uid, and the person an executor is inviting has, by definition,
 * never used Steward. The endpoint defaults it off for scripts; from the UI,
 * filling in this form *is* the deliberate act it guards.
 */
export async function inviteToEstate(
  estateId: string,
  invite: { email: string; role: 'executor' | 'beneficiary'; display_name?: string },
): Promise<Membership> {
  const response = await authorizedFetch(
    `/estates/${encodeURIComponent(estateId)}/invite`,
    { method: 'POST', body: { ...invite, create_account: true } },
  )
  return (await response.json()) as Membership
}

/** Accept the invite waiting on this estate. Idempotent server-side; the
 * response says whether this call is what actually flipped it. */
export async function acceptInvite(estateId: string): Promise<Membership> {
  const response = await authorizedFetch(
    `/estates/${encodeURIComponent(estateId)}/accept`,
    { method: 'POST' },
  )
  return (await response.json()) as Membership
}

export async function fetchItemResolution(
  itemId: string,
): Promise<ResolutionDetail | null> {
  const response = await authorizedFetch(
    `/items/${encodeURIComponent(itemId)}/resolution`,
  )
  return (await response.json()) as ResolutionDetail | null
}

export async function resolveItem(
  itemId: string,
  body: {
    resolution_type: ResolutionType
    resolved_to_user_id?: string | null
    notes?: string
  },
): Promise<void> {
  await authorizedFetch(`/items/${encodeURIComponent(itemId)}/resolve`, {
    method: 'POST',
    body: {
      resolution_type: body.resolution_type,
      resolved_to_user_id: body.resolved_to_user_id ?? null,
      notes: body.notes?.trim() ?? '',
    },
  })
}

/** Every item with its claim count and its decision, in one request. */
export async function fetchReview(estateId: string): Promise<ReviewResponse> {
  const response = await authorizedFetch(`/estates/${encodeURIComponent(estateId)}/review`)
  return (await response.json()) as ReviewResponse
}

/** Attach a photograph to an item. Executor only, enforced server-side. */
/** Catalogue a new belonging from a photograph.
 *
 * Slow on purpose: a real Gemini call sits inside it. The caller has to say so
 * rather than leave the executor watching nothing happen. */
export async function addEstateItem(
  estateId: string,
  file: File,
  acceptAnyway = false,
): Promise<Item> {
  const form = new FormData()
  form.append('file', file)
  const response = await authorizedFetch(
    `/estates/${encodeURIComponent(estateId)}/items${acceptAnyway ? '?accept_anyway=true' : ''}`,
    { method: 'POST', form },
  )
  return (await response.json()) as Item
}

/** Take an item off the list. Executor only, and idempotent — the document and
 * everything attached to it stay exactly where they are. */
export async function removeItem(itemId: string): Promise<Item> {
  const response = await authorizedFetch(`/items/${encodeURIComponent(itemId)}/remove`, {
    method: 'POST',
  })
  return (await response.json()) as Item
}

export interface WithdrawResponse {
  item_id: string
  withdrawn: number
  status: string
}

/** Take your own name back off an item. You can only ever withdraw your own —
 * the server reads the caller from the token, not from anything sent. */
export async function withdrawClaim(itemId: string): Promise<WithdrawResponse> {
  const response = await authorizedFetch(`/items/${encodeURIComponent(itemId)}/claim`, {
    method: 'DELETE',
  })
  return (await response.json()) as WithdrawResponse
}

/** Answer the agent's question about an item it couldn't place.
 *
 * Slow: a real Gemini call, with the original photograph and these words
 * together. Any accepted member may answer. */
export async function clarifyItem(itemId: string, text: string): Promise<ClarifyResponse> {
  const response = await authorizedFetch(`/items/${encodeURIComponent(itemId)}/clarify`, {
    method: 'POST',
    body: { text },
  })
  return (await response.json()) as ClarifyResponse
}

export async function uploadItemPhoto(itemId: string, file: File): Promise<Item> {
  const form = new FormData()
  form.append('file', file)
  const response = await authorizedFetch(`/items/${encodeURIComponent(itemId)}/photo`, {
    method: 'POST',
    form,
  })
  return (await response.json()) as Item
}

export async function fetchItemDisposition(
  itemId: string,
): Promise<DispositionDetail | null> {
  const response = await authorizedFetch(
    `/items/${encodeURIComponent(itemId)}/disposition`,
  )
  return (await response.json()) as DispositionDetail | null
}

/** Record where a resolved item is headed. Executor only, enforced server-side. */
export async function decideDisposition(
  itemId: string,
  choice: DispositionChoice,
): Promise<void> {
  await authorizedFetch(`/items/${encodeURIComponent(itemId)}/disposition`, {
    method: 'POST',
    body: { executor_chosen_disposition: choice },
  })
}

/** Ask Steward where to list it. Only meaningful after a `sell` decision. */
/** Mark the next thing that actually happened to a disposition. Executor only,
 * one step per call. */
export async function advanceDisposition(itemId: string): Promise<DispositionDetail> {
  const response = await authorizedFetch(
    `/items/${encodeURIComponent(itemId)}/disposition/advance`,
    { method: 'POST' },
  )
  return (await response.json()) as DispositionDetail
}

export async function requestListing(itemId: string): Promise<ListingDetail> {
  const response = await authorizedFetch(
    `/items/${encodeURIComponent(itemId)}/marketplace-listing`,
    { method: 'POST' },
  )
  return (await response.json()) as ListingDetail
}
