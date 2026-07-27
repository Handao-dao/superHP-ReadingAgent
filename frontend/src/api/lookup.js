export async function lookupWord(
  word,
  sentence = '',
  profileId = '',
  unitId = '',
  wasAnnotated = false,
) {
  const response = await fetch('/api/word-lookup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      word,
      sentence,
      profile_id: profileId || undefined,
      unit_id: unitId || undefined,
      was_annotated: Boolean(wasAnnotated),
    }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || '查词失败')
  }
  return response.json()
}
