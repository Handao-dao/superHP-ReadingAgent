/**
 * Owns the temporary manual reading conversation visible in the drawer.
 * The backend remains the authority for the frozen Episode reading context.
 * This composable does not open the drawer or inspect DOM text selections.
 */
import { computed, ref } from 'vue'
import {
  createReadingCompanionSession,
  getReadingCompanionSession,
  retryReadingCompanionSession,
  sendReadingCompanionMessage,
} from '../api/readingCompanion'

const SESSION_STORAGE_KEY = 'superhp_reading_companion_session_id'
const RETRYABLE_ERRORS = new Set(['model_error', 'invalid_model_response'])

export function useReadingCompanion() {
  const session = ref(null)
  const storedSessionId = ref(localStorage.getItem(SESSION_STORAGE_KEY) || '')
  const loading = ref(false)
  const errorMessage = ref('')

  const hasSession = computed(() => Boolean(session.value?.session_id))
  const messages = computed(() => session.value?.messages || [])
  const errorCode = computed(() => session.value?.error_code || '')
  const canRetry = computed(() => (
    RETRYABLE_ERRORS.has(errorCode.value)
    && !loading.value
  ))
  const canSend = computed(() => (
    hasSession.value
    && !canRetry.value
    && !loading.value
  ))

  function rememberSession(nextSession) {
    session.value = nextSession
    storedSessionId.value = nextSession.session_id
    localStorage.setItem(SESSION_STORAGE_KEY, nextSession.session_id)
    return nextSession
  }

  function clearSession() {
    session.value = null
    storedSessionId.value = ''
    errorMessage.value = ''
    localStorage.removeItem(SESSION_STORAGE_KEY)
  }

  async function restoreSession() {
    const sessionId = storedSessionId.value
    if (!sessionId || loading.value) return null
    loading.value = true
    errorMessage.value = ''
    try {
      return rememberSession(await getReadingCompanionSession(sessionId))
    } catch (error) {
      if (error.status === 404) {
        // The current backend intentionally stores manual chats in memory.
        // A restart makes the browser's old id harmless and disposable.
        clearSession()
        return null
      }
      errorMessage.value = error.message || '阅读助手对话恢复失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function startSession({ currentUnitId, message, selectedText = '' }) {
    const content = String(message || '').trim()
    const unitId = String(currentUnitId || '').trim()
    if (!content || !unitId || loading.value) return null
    loading.value = true
    errorMessage.value = ''
    try {
      return rememberSession(await createReadingCompanionSession({
        current_unit_id: unitId,
        message: content,
        selected_text: String(selectedText || '').trim(),
      }))
    } catch (error) {
      errorMessage.value = error.message || '阅读助手对话创建失败'
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
      return rememberSession(await sendReadingCompanionMessage(
        session.value.session_id,
        content,
      ))
    } catch (error) {
      errorMessage.value = error.message || '阅读助手消息发送失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function retrySession() {
    if (!session.value?.session_id || !canRetry.value) return null
    loading.value = true
    errorMessage.value = ''
    try {
      return rememberSession(
        await retryReadingCompanionSession(session.value.session_id),
      )
    } catch (error) {
      errorMessage.value = error.message || '阅读助手对话重试失败'
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    canRetry,
    canSend,
    clearSession,
    errorCode,
    errorMessage,
    hasSession,
    loading,
    messages,
    restoreSession,
    retrySession,
    sendMessage,
    session,
    startSession,
  }
}
