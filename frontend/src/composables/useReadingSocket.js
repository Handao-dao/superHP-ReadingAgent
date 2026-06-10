import { computed, onBeforeUnmount, ref } from 'vue'

function makeRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function readingSocketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/reading`
}

export function useReadingSocket() {
  const cards = ref([])
  const activeChapter = ref(null)
  const currentChapterId = ref(null)
  const connected = ref(false)
  const busy = ref(false)
  const statusMessage = ref('正在连接阅读会话...')
  const noticeMessage = ref('')
  const errorMessage = ref('')

  let socket = null
  let intentionalClose = false

  const canSend = computed(() => connected.value && socket?.readyState === WebSocket.OPEN)

  function connect() {
    if (socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) return

    intentionalClose = false
    errorMessage.value = ''
    noticeMessage.value = ''
    statusMessage.value = '正在连接阅读会话...'

    socket = new WebSocket(readingSocketUrl())

    socket.addEventListener('open', () => {
      connected.value = true
      statusMessage.value = '阅读会话已连接'
      send({ type: 'hello', request_id: makeRequestId(), current_chapter_id: currentChapterId.value })
    })

    socket.addEventListener('message', (event) => {
      handleEvent(JSON.parse(event.data))
    })

    socket.addEventListener('close', () => {
      connected.value = false
      busy.value = false
      statusMessage.value = intentionalClose ? '阅读会话已关闭' : '阅读会话已断开'
    })

    socket.addEventListener('error', () => {
      errorMessage.value = '阅读会话连接异常，请确认后端服务已启动。'
      statusMessage.value = '阅读会话异常'
    })
  }

  function disconnect() {
    intentionalClose = true
    socket?.close()
    socket = null
  }

  function send(payload) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      errorMessage.value = '阅读会话尚未连接。'
      return false
    }
    socket.send(JSON.stringify(payload))
    return true
  }

  function sendAction(action) {
    errorMessage.value = ''
    noticeMessage.value = ''
    busy.value = true

    const sent = send({
      type: 'action',
      request_id: makeRequestId(),
      action,
    })

    if (!sent) busy.value = false
  }

  function handleEvent(message) {
    switch (message.type) {
      case 'ready':
        connected.value = true
        statusMessage.value = '阅读会话已连接'
        return
      case 'cards.updated':
        cards.value = message.cards || []
        currentChapterId.value = message.current_chapter_id || currentChapterId.value
        busy.value = false
        return
      case 'chapter.loading':
        busy.value = true
        statusMessage.value = '正在加载章节...'
        return
      case 'chapter.opened':
        activeChapter.value = message.chapter
        currentChapterId.value = message.chapter?.meta?.id || currentChapterId.value
        statusMessage.value = '章节已打开'
        return
      case 'annotation.started':
        busy.value = true
        noticeMessage.value = '开始生成译注...'
        return
      case 'annotation.progress':
        busy.value = true
        noticeMessage.value = message.message || '正在生成译注...'
        return
      case 'annotation.completed':
        busy.value = false
        noticeMessage.value = '译注已生成'
        return
      case 'annotation.failed':
        errorMessage.value = message.message || '译注生成失败。'
        busy.value = false
        return
      case 'annotation.not_ready':
        noticeMessage.value = message.message || '该功能尚未接入。'
        busy.value = false
        return
      case 'error':
        errorMessage.value = message.error?.message || '阅读会话发生错误。'
        busy.value = false
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
    errorMessage,
    noticeMessage,
    statusMessage,
    connect,
    disconnect,
    sendAction,
  }
}