/** Calls to the backend API, with the caller's ID token attached.
 *
 * getIdToken() returns the cached token and refreshes it when it's close to
 * expiring, so this asks for it per request rather than holding one that will
 * quietly go stale after an hour.
 */

import { auth, API_BASE_URL } from './firebase'
import type { ItemListResponse } from './types'

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function authorizedFetch(path: string): Promise<Response> {
  const user = auth.currentUser
  if (!user) throw new ApiError(401, 'You are signed out. Sign in again to continue.')

  const token = await user.getIdToken()

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
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
