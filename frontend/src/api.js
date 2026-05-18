const BASE = '/api'

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

export async function api(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (res.status === 401) {
    throw new ApiError(401, 'Unauthorized')
  }
  if (!res.ok) throw new ApiError(res.status, `API error ${res.status}`)
  if (res.status === 204) return null
  return res.json()
}

export const get = (path) => api(path)
export const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body) })
export const patch = (path, body) => api(path, { method: 'PATCH', body: JSON.stringify(body) })
