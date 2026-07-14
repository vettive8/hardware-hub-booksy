const TOKEN_KEY = 'hardware-hub-token'

export const session = {
  get token() { return localStorage.getItem(TOKEN_KEY) },
  set token(value) { value ? localStorage.setItem(TOKEN_KEY, value) : localStorage.removeItem(TOKEN_KEY) },
}

export async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (session.token) headers.Authorization = `Bearer ${session.token}`
  const response = await fetch(`/api${path}`, { ...options, headers })

  // An expired token would otherwise leave the UI logged in and inert: every call
  // fails while the session still looks alive. Drop it and fall back to the login view.
  if (response.status === 401 && session.token) {
    session.token = null
    window.dispatchEvent(new CustomEvent('session-expired'))
  }

  if (response.status === 204) return null
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((item) => item.msg).join(', ') : body.detail
    throw new Error(detail || 'Something went wrong')
  }
  return body
}

