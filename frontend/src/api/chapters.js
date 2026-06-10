export async function listChapters() {
  const response = await fetch('/api/units')
  if (!response.ok) throw new Error('阅读单元列表加载失败')
  return response.json()
}