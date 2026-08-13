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
  MessageListResponse,
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
    // A dead backend is the likeliest cause in local development, and a blank
    // screen would leave someone guessing.
    throw new ApiError(
      0,
      `Couldn't reach the backend at ${API_BASE_URL}. Is it running? ` +
        '(cd backend && .venv/bin/uvicorn api:app --reload)',
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
