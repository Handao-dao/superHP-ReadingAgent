/** Persist explicit choices made on the chapter-end difficulty prompt. */

async function requestJson(url, options = {}) {
  const response = await fetch(url, options)
  if (response.ok) return response.json()
  let detail = ''
  try {
    detail = (await response.json())?.detail || ''
  } catch {
    // A proxy or server error may return a non-JSON body.
  }
  const error = new Error(detail || '阅读选择暂时无法保存')
  error.status = response.status
  throw error
}

export function continueReadingAfterDifficulty(bookId) {
  return requestJson(
    `/api/reading-difficulty-prompts/${encodeURIComponent(bookId)}/continue`,
    { method: 'POST' },
  )
}
