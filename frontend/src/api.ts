/** Calls to the backend API, with the caller's ID token attached.
 *
 * getIdToken() returns the cached token and refreshes it when it's close to
 * expiring, so this asks for it per request rather than holding one that will
 * quietly go stale after an hour.
 */

import { auth, API_BASE_URL } from './firebase'
import type {
  ClaimListResponse,
  Item,
  ItemListResponse,
  Me,
  Message,
  MessageListResponse,
  ResolutionDetail,
  ResolutionType,
  ReviewResponse,
} from './types'

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function authorizedFetch(
  path: string,
  init?: { method?: string; body?: unknown },
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
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: init?.body ? JSON.stringify(init.body) : undefined,
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
    throw new ApiError(response.status, detail ?? `Request failed (${response.status}).`)
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
