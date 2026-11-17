// A small wrapper around fetch: adds the access token, refreshes it once when it has
// expired, and turns error responses (RFC 9457 problem details) into ApiError.

const TOKENS_KEY = 'booking.tokens'

export type Tokens = { access: string; refresh: string }

export class ApiError extends Error {
  status: number
  code?: string

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export function getTokens(): Tokens | null {
  const saved = localStorage.getItem(TOKENS_KEY)
  return saved ? (JSON.parse(saved) as Tokens) : null
}

export function setTokens(tokens: Tokens | null) {
  if (tokens) {
    localStorage.setItem(TOKENS_KEY, JSON.stringify(tokens))
  } else {
    localStorage.removeItem(TOKENS_KEY)
  }
  // Lets the auth context know, including when a refresh failed deep inside a request.
  window.dispatchEvent(new Event('tokens-changed'))
}

type Params = Record<string, string | number | string[] | undefined | null>

type Options = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  params?: Params
  body?: unknown
}

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  let response = await send(path, options)
  if (response.status === 401 && getTokens() && (await refreshTokens())) {
    response = await send(path, options)
  }
  if (!response.ok) {
    throw await toError(response)
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

function send(path: string, { method = 'GET', params, body }: Options): Promise<Response> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params ?? {})) {
    // Lists are sent as repeated keys: ?amenities=wifi&amenities=pool
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item !== undefined && item !== null && item !== '') {
        query.append(key, String(item))
      }
    }
  }
  const url = query.size ? `${path}?${query}` : path

  const headers: Record<string, string> = {}
  const tokens = getTokens()
  if (tokens) headers.Authorization = `Bearer ${tokens.access}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  return fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
}

async function refreshTokens(): Promise<boolean> {
  const tokens = getTokens()
  if (!tokens) return false
  const response = await fetch('/api/v1/auth/token/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh: tokens.refresh }),
  })
  if (!response.ok) {
    setTokens(null) // the refresh token expired too: the user has to log in again
    return false
  }
  setTokens((await response.json()) as Tokens)
  return true
}

async function toError(response: Response): Promise<ApiError> {
  if (response.status === 429) {
    const seconds = response.headers.get('Retry-After')
    return new ApiError(429, `Too many requests. Try again in ${seconds ?? 'a few'} seconds.`)
  }
  try {
    const problem = await response.json()
    return new ApiError(response.status, firstFieldError(problem.errors) ?? problem.detail, problem.code)
  } catch {
    return new ApiError(response.status, `Request failed (${response.status}).`)
  }
}

// Catalog reports field errors as {field: [messages]}, Booking as [{loc, msg}].
function firstFieldError(errors: unknown): string | undefined {
  if (Array.isArray(errors)) {
    return errors[0]?.msg
  }
  if (errors && typeof errors === 'object') {
    const [field, messages] = Object.entries(errors)[0] ?? []
    if (Array.isArray(messages)) return `${field}: ${messages[0]}`
  }
  return undefined
}
