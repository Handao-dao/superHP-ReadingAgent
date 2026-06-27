export async function listProfiles() {
  const response = await fetch('/api/profiles')
  if (!response.ok) throw new Error('阅读场景列表加载失败')
  return response.json()
}
