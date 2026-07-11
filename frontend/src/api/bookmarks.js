const BASE = '/api/bookmarks'

async function readError(response, fallback) {
  const detail = await response.json().catch(() => null)
  return detail?.detail || fallback
}

export async function fetchBookmarks({ unitId = '' } = {}) {
  const params = new URLSearchParams()
  if (unitId) params.set('unit_id', unitId)
  const query = params.toString()
  const response = await fetch(query ? `${BASE}?${query}` : BASE)
  if (!response.ok) throw new Error(await readError(response, '书签加载失败'))
  return response.json()
}

export async function addBookmark({
  unitId,
  bodyKind,
  pageIndex,
  progressRatio,
  totalPages,
  label,
  excerpt,
  paragraphIndex,
}) {
  const response = await fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      unit_id: unitId,
      body_kind: bodyKind,
      page_index: pageIndex,
      progress_ratio: progressRatio,
      total_pages: totalPages,
      label,
      excerpt,
      paragraph_index: paragraphIndex,
    }),
  })
  if (!response.ok) throw new Error(await readError(response, '保存书签失败'))
  return response.json()
}

export async function deleteBookmark(bookmarkId) {
  const response = await fetch(`${BASE}/${bookmarkId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error(await readError(response, '删除书签失败'))
  return response.json()
}
