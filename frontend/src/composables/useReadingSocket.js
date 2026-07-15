import { computed, onBeforeUnmount, ref, watch } from 'vue'

const CURRENT_UNIT_STORAGE_KEY = 'superhp_current_unit_id'

function makeRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function readingSocketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/reading`
}

function userFacingError(message, fallback = '阅读会话发生错误。') {
  const text = String(message || '').trim()
  if (!text) return fallback
  if (text.includes('Unable to extract JSON') || text.includes('valid annotation JSON')) {
    return '模型返回格式不符合要求，译注生成失败。请稍后重试或先阅读原文。'
  }
  const compact = text.replace(/\s+/g, ' ')
  return compact.length > 96 ? `${compact.slice(0, 96)}...` : compact
}

export function useReadingSocket(options = {}) {
  const cards = ref([])
  const activeChapter = ref(null)
  const currentChapterId = ref(localStorage.getItem(CURRENT_UNIT_STORAGE_KEY) || null)
  const connected = ref(false)
  const busy = ref(false)
  const loadStatus = ref('connecting')
  const statusMessage = ref('正在连接阅读会话...')
  const noticeMessage = ref('')
  const progressMessage = ref('')
  const errorMessage = ref('')
  const cardsRevision = ref(0)
  const degradationCounts = ref({ provider: 0, validation: 0, other: 0 })

  let socket = null
  let intentionalClose = false

  const canSend = computed(() => connected.value && socket?.readyState === WebSocket.OPEN)
  const selectedProfileId = () => options.profileId?.value || options.profileId || ''
  const annotationWarning = computed(() => {
    const { provider, validation, other } = degradationCounts.value
    const parts = []
    if (provider) parts.push(`${provider} 个分块在模型调用重试后仍失败`)
    if (validation) parts.push(`${validation} 个分块未通过格式或原文校验`)
    if (other) parts.push(`${other} 个分块未能生成有效译注`)
    if (!parts.length) return ''
    return `${parts.join('，')}，已回退为原文；其他分块仍可正常阅读。`
  })

  function resetAnnotationWarning() {
    degradationCounts.value = { provider: 0, validation: 0, other: 0 }
  }

  function recordDegradedChunk(category) {
    const key = ['provider', 'validation'].includes(category) ? category : 'other'
    degradationCounts.value = {
      ...degradationCounts.value,
      [key]: degradationCounts.value[key] + 1,
    }
  }

  watch(currentChapterId, (unitId) => {
    if (unitId) {
      localStorage.setItem(CURRENT_UNIT_STORAGE_KEY, unitId)
    } else {
      localStorage.removeItem(CURRENT_UNIT_STORAGE_KEY)
    }
  })

  function connect() {
    if (socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) return

    intentionalClose = false
    errorMessage.value = ''
    noticeMessage.value = ''
    progressMessage.value = ''
    loadStatus.value = 'connecting'
    statusMessage.value = '正在连接阅读会话...'

    socket = new WebSocket(readingSocketUrl())

    socket.addEventListener('open', () => {
      connected.value = true
      loadStatus.value = 'idle'
      statusMessage.value = '阅读会话已连接'
      send({
        type: 'hello',
        request_id: makeRequestId(),
        current_unit_id: currentChapterId.value,
        profile_id: selectedProfileId(),
      })
    })

    socket.addEventListener('message', (event) => {
      try {
        handleEvent(JSON.parse(event.data))
      } catch {
        errorMessage.value = userFacingError('', '阅读事件解析失败。')
        loadStatus.value = 'failed'
      }
    })

    socket.addEventListener('close', () => {
      connected.value = false
      busy.value = false
      loadStatus.value = intentionalClose ? 'idle' : 'offline'
      statusMessage.value = intentionalClose ? '阅读会话已关闭' : '阅读会话已断开'
    })

    socket.addEventListener('error', () => {
      errorMessage.value = userFacingError('', '阅读会话连接异常，请确认后端服务已启动。')
      statusMessage.value = '阅读会话异常'
      loadStatus.value = 'failed'
    })
  }

  function disconnect() {
    intentionalClose = true
    socket?.close()
    socket = null
  }

  function send(payload) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      errorMessage.value = userFacingError('', '阅读会话尚未连接。')
      loadStatus.value = 'failed'
      return false
    }
    socket.send(JSON.stringify(payload))
    return true
  }

  function sendAction(action) {
    errorMessage.value = ''
    noticeMessage.value = ''
    progressMessage.value = ''
    busy.value = true

    const sent = send({
      type: 'action',
      request_id: makeRequestId(),
      action,
    })

    if (!sent) busy.value = false
  }

  function requestCards(phase = 'start', unitId = currentChapterId.value) {
    errorMessage.value = ''
    const targetUnitId = unitId || currentChapterId.value
    const sent = send({
      type: 'cards',
      request_id: makeRequestId(),
      current_unit_id: targetUnitId,
      profile_id: selectedProfileId(),
      phase,
    })
    if (sent && targetUnitId) {
      currentChapterId.value = targetUnitId
      if (activeChapter.value?.meta?.id !== targetUnitId) activeChapter.value = null
    }
    return sent
  }

  function handleEvent(message) {
    switch (message.type) {
      case 'ready':
        connected.value = true
        loadStatus.value = 'idle'
        statusMessage.value = '阅读会话已连接'
        return
      case 'cards.updated':
        if (message.current_unit_id && activeChapter.value?.meta?.id !== message.current_unit_id) {
          activeChapter.value = null
        }
        cards.value = message.cards || []
        currentChapterId.value = message.current_unit_id || currentChapterId.value
        cardsRevision.value += 1
        busy.value = false
        if (!['failed', 'offline'].includes(loadStatus.value)) loadStatus.value = 'idle'
        return
      case 'chapter.loading':
        resetAnnotationWarning()
        currentChapterId.value = message.unit_id || currentChapterId.value
        busy.value = true
        loadStatus.value = 'loading_unit'
        progressMessage.value = message.body_kind === 'annotated' ? 'Opening annotated copy...' : 'Loading original text...'
        statusMessage.value = 'Loading reading unit...'
        return
      case 'chapter.opened':
        activeChapter.value = message.unit
        currentChapterId.value = activeChapter.value?.meta?.id || currentChapterId.value
        statusMessage.value = 'Reading unit opened'
        progressMessage.value = ''
        noticeMessage.value = annotationWarning.value
        loadStatus.value = 'idle'
        return
      case 'annotation.started':
        resetAnnotationWarning()
        currentChapterId.value = message.unit_id || currentChapterId.value
        busy.value = true
        loadStatus.value = 'generating_annotation'
        noticeMessage.value = 'Starting annotation...'
        progressMessage.value = 'Starting annotation...'
        return
      case 'annotation.progress':
        currentChapterId.value = message.unit_id || currentChapterId.value
        busy.value = true
        loadStatus.value = 'generating_annotation'
        progressMessage.value = message.message || 'Generating annotations...'
        noticeMessage.value = progressMessage.value
        return
      case 'annotation.model_retry':
        busy.value = true
        loadStatus.value = 'model_retrying'
        progressMessage.value = message.message || 'Model request failed, retrying...'
        noticeMessage.value = progressMessage.value
        return
      case 'annotation.degraded':
        recordDegradedChunk(message.category)
        noticeMessage.value = annotationWarning.value
        return
      case 'annotation.completed':
        if (message.status === 'degraded') {
          degradationCounts.value = {
            provider: Number(message.provider_error_count) || 0,
            validation: Number(message.validation_error_count) || 0,
            other: Math.max(
              0,
              (Number(message.degraded_chunk_count) || 0)
                - (Number(message.provider_error_count) || 0)
                - (Number(message.validation_error_count) || 0),
            ),
          }
        } else {
          resetAnnotationWarning()
        }
        busy.value = false
        loadStatus.value = 'completed'
        progressMessage.value = 'Annotations ready'
        noticeMessage.value = annotationWarning.value || 'Annotations ready'
        return
      case 'annotation.failed':
        errorMessage.value = userFacingError(message.message, '译注生成失败。')
        progressMessage.value = ''
        busy.value = false
        loadStatus.value = 'failed'
        return
      case 'error':
        errorMessage.value = userFacingError(message.error?.message, '阅读会话发生错误。')
        progressMessage.value = ''
        busy.value = false
        loadStatus.value = 'failed'
        return
      case 'pong':
        return
      default:
        return
    }
  }

  onBeforeUnmount(disconnect)

  return {
    activeChapter,
    annotationWarning,
    busy,
    canSend,
    cardsRevision,
    cards,
    connected,
    currentChapterId,
    errorMessage,
    loadStatus,
    noticeMessage,
    progressMessage,
    statusMessage,
    connect,
    disconnect,
    requestCards,
    sendAction,
  }
}
