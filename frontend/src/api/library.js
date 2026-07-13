export async function listLibraryCollections() {
  const response = await fetch('/api/library')
  if (!response.ok) throw new Error('书库结构加载失败')
  return response.json()
}
