const BASE = '/api/vocabulary'

export async function fetchVocabulary({ unitId = '', chapterId = '', profileId = '' } = {}) {
  const params = new URLSearchParams()
  if (unitId) params.set('unit_id', unitId)
  if (chapterId) params.set('chapter_id', chapterId)
  if (profileId) params.set('profile_id', profileId)
  const query = params.toString()
  const response = await fetch(query ? `${BASE}?${query}` : BASE)
  if (!response.ok) throw new Error('生词表加载失败')
  const items = await response.json()
  return { items, total: items.length }
}

export async function addVocabulary({ word, translation, context, pos = 'other', unitId }) {
  const response = await fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      word,
      translation,
      context,
      pos,
      unit_id: unitId,
    }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || '添加生词失败')
  }
  return response.json()
}

export async function setMastered(vocabId, mastered) {
  const response = await fetch(`${BASE}/${vocabId}/master`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mastered }),
  })
  if (!response.ok) throw new Error('更新掌握状态失败')
  return response.json()
}

export async function setMasteredByWord(word, mastered, profileId = '') {
  const response = await fetch(`${BASE}/mark-by-word`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ word, mastered, profile_id: profileId || undefined }),
  })
  if (!response.ok) throw new Error('更新掌握状态失败')
  return response.json()
}

export async function deleteVocabulary(vocabId) {
  const response = await fetch(`${BASE}/${vocabId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('删除生词失败')
  return response.json()
}
