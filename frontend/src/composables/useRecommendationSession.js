/**
 * Owns one durable recommendation conversation and its request state.
 * The page coordinator decides when to show the conversation.
 * This composable does not render messages or change the active application view.
 */
import { computed, ref } from 'vue'
import {
  createRecommendationSession,
  getRecommendationSession,
  sendRecommendationMessage,
} from '../api/recommendations'

const SESSION_STORAGE_KEY = 'superhp_recommendation_session_id'

export function useRecommendationSession() {
  const session = ref(null)
  const storedSessionId = ref(localStorage.getItem(SESSION_STORAGE_KEY) || '')
  const loading = ref(false)
  const errorMessage = ref('')

  const hasSession = computed(() => Boolean(session.value?.session_id))
  const hasStoredSession = computed(() => Boolean(storedSessionId.value))
  const messages = computed(() => session.value?.messages || [])
  const recommendedBooks = computed(() => session.value?.recommended_books || [])
  const phase = computed(() => session.value?.phase || '')
  const canSend = computed(() => phase.value === 'awaiting_user' && !loading.value)

  async function restoreSession() {
    const sessionId = storedSessionId.value
    if (!sessionId || loading.value) return null
    loading.value = true
    errorMessage.value = ''
    try {
      session.value = await getRecommendationSession(sessionId)
      return session.value
    } catch (error) {
      if (error.status === 404) {
        localStorage.removeItem(SESSION_STORAGE_KEY)
        storedSessionId.value = ''
        session.value = null
      }
      errorMessage.value = error.message || '历史选书对话恢复失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function startSession() {
    if (loading.value) return null
    loading.value = true
    errorMessage.value = ''
    try {
      session.value = await createRecommendationSession()
      storedSessionId.value = session.value.session_id
      localStorage.setItem(SESSION_STORAGE_KEY, session.value.session_id)
      return session.value
    } catch (error) {
      errorMessage.value = error.message || '选书对话创建失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function sendMessage(message) {
    const content = String(message || '').trim()
    if (!content || !session.value?.session_id || !canSend.value) return null
    loading.value = true
    errorMessage.value = ''
    try {
      session.value = await sendRecommendationMessage(
        session.value.session_id,
        content,
      )
      return session.value
    } catch (error) {
      errorMessage.value = error.message || '消息发送失败'
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    canSend,
    errorMessage,
    hasSession,
    hasStoredSession,
    loading,
    messages,
    phase,
    recommendedBooks,
    restoreSession,
    sendMessage,
    session,
    startSession,
  }
}
