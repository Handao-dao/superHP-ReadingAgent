/** Load reading-unit metadata; grouping units into books belongs to the catalog layer. */
export async function listUnits(profileId = '') {
  const params = new URLSearchParams()
  if (profileId) params.set('profile_id', profileId)
  const query = params.toString()
  const response = await fetch(`/api/units${query ? `?${query}` : ''}`)
  if (!response.ok) throw new Error('阅读单元列表加载失败')
  return response.json()
}
