/** Call the durable recommendation HTTP API without owning Vue state or navigation. */

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
  const error = new Error(detail || '选书助手暂时无法响应')
  error.status = response.status
  throw error
}

export function createRecommendationSession(payload = {}) {
  return requestJson('/api/recommendations/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function createDifficultyRecommendationHandoff(payload) {
  return requestJson('/api/recommendations/difficulty-handoffs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function getRecommendationSession(sessionId) {
  return requestJson(`/api/recommendations/sessions/${encodeURIComponent(sessionId)}`)
}

export function sendRecommendationMessage(sessionId, message) {
  return requestJson(`/api/recommendations/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
}
