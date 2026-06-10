import { computed, onBeforeUnmount, ref } from 'vue'

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

export function useReadingSocket() {
  const cards = ref([])
  const activeChapter = ref(null)
  const currentChapterId = ref(null)
  const connected = ref(false)
  const busy = ref(false)
  const loadStatus = ref('connecting')
  const statusMessage = ref('正在连接阅读会话...')
  const noticeMessage = ref('')
  const progressMessage = ref('')
  const errorMessage = ref('')

  let socket = null
  let intentionalClose = false

  const canSend = computed(() => connected.value && socket?.readyState === WebSocket.OPEN)

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
        current_chapter_id: currentChapterId.value,
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

  function requestCards(phase = 'start') {
    return send({
      type: 'cards',
      request_id: makeRequestId(),
      current_unit_id: currentChapterId.value,
      current_chapter_id: currentChapterId.value,
      phase,
    })
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
        currentChapterId.value = message.current_unit_id || message.current_chapter_id || currentChapterId.value
        busy.value = false
        if (!['failed', 'offline'].includes(loadStatus.value)) loadStatus.value = 'idle'
        return
      case 'chapter.loading':
        busy.value = true
        loadStatus.value = 'loading_unit'
        progressMessage.value = message.body_kind === 'annotated' ? '正在打开译注副本...' : '正在加载原文...'
        statusMessage.value = '正在加载阅读单元...'
        return
      case 'chapter.opened':
        activeChapter.value = message.unit || message.chapter
        currentChapterId.value = activeChapter.value?.meta?.id || currentChapterId.value
        statusMessage.value = '阅读单元已打开'
        progressMessage.value = ''
        noticeMessage.value = ''
        loadStatus.value = 'idle'
        return
      case 'annotation.started':
        busy.value = true
        loadStatus.value = 'generating_annotation'
        noticeMessage.value = '开始生成译注...'
        progressMessage.value = '开始生成译注...'
        return
      case 'annotation.progress':
        busy.value = true
        loadStatus.value = 'generating_annotation'
        progressMessage.value = message.message || '正在生成译注...'
        noticeMessage.value = progressMessage.value
        return
      case 'annotation.model_retry':
        busy.value = true
        loadStatus.value = 'model_retrying'
        progressMessage.value = message.message || 'Model request failed, retrying...'
        noticeMessage.value = progressMessage.value
        return
      case 'annotation.json_repair':
        busy.value = true
        loadStatus.value = 'json_repairing'
        progressMessage.value = message.message || '模型返回格式异常，正在修复...'
        noticeMessage.value = progressMessage.value
        return
      case 'annotation.completed':
        busy.value = false
        loadStatus.value = 'completed'
        progressMessage.value = '译注已生成'
        noticeMessage.value = '译注已生成'
        return
      case 'annotation.failed':
        errorMessage.value = userFacingError(message.message, '译注生成失败。')
        progressMessage.value = ''
        busy.value = false
        loadStatus.value = 'failed'
        return
      case 'annotation.not_ready':
        noticeMessage.value = message.message || '该功能尚未接入。'
        progressMessage.value = noticeMessage.value
        busy.value = false
        loadStatus.value = 'idle'
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
    busy,
    canSend,
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
