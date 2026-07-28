/** Call the temporary reading-companion HTTP API without owning Vue state. */

const BASE = '/api/reading-companion/sessions'

async function requestJson(url, options = {}) {
  const response = await fetch(url, options)
  if (response.ok) return response.json()

  let detail = ''
  try {
    const payload = await response.json()
    detail = typeof payload?.detail === 'string' ? payload.detail : ''
  } catch {
    // A proxy or server error may return a non-JSON body.
  }
  const error = new Error(detail || '阅读助手暂时无法响应')
  error.status = response.status
  throw error
}

export function createReadingCompanionSession(payload) {
  return requestJson(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function getReadingCompanionSession(sessionId) {
  return requestJson(`${BASE}/${encodeURIComponent(sessionId)}`)
}

export function retryReadingCompanionSession(sessionId) {
  return requestJson(`${BASE}/${encodeURIComponent(sessionId)}/retry`, {
    method: 'POST',
  })
}

export function sendReadingCompanionMessage(sessionId, message) {
  return requestJson(`${BASE}/${encodeURIComponent(sessionId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
}
