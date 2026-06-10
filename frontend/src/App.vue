<script setup>
import { onMounted, ref } from 'vue'
import { listChapters } from './api/chapters'
import { useReadingSocket } from './composables/useReadingSocket'

const chapters = ref([])
const listLoading = ref(false)
const listErrorMessage = ref('')

const {
  activeChapter,
  busy,
  canSend,
  cards,
  connected,
  errorMessage,
  noticeMessage,
  statusMessage,
  connect,
  sendAction,
} = useReadingSocket()

async function loadChapterList() {
  listLoading.value = true
  listErrorMessage.value = ''
  try {
    chapters.value = await listChapters()
  } catch (error) {
    listErrorMessage.value = error.message || '阅读单元列表加载失败'
  } finally {
    listLoading.value = false
  }
}

function handleAction(action) {
  sendAction(action)
}

onMounted(() => {
  loadChapterList()
  connect()
})
</script>

<template>
  <main class="app-shell">
    <section class="agent-panel">
      <div class="brand-row">
        <div>
          <p class="eyebrow">SuperHP Agent</p>
          <h1>章节阅读助手</h1>
        </div>
        <span class="status-pill" :class="{ 'is-online': connected }">{{ connected ? '在线' : '离线' }}</span>
      </div>

      <p class="muted">{{ statusMessage }}</p>
      <p v-if="busy || listLoading" class="muted">正在加载...</p>
      <p v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</p>
      <p v-if="errorMessage || listErrorMessage" class="error-text">
        {{ errorMessage || listErrorMessage }}
      </p>

      <div class="card-list">
        <article v-for="card in cards" :key="card.id" class="agent-card">
          <p class="card-type">{{ card.type }}</p>
          <h2>{{ card.title }}</h2>
          <p>{{ card.body }}</p>
          <div class="actions">
            <button
              v-for="action in card.actions"
              :key="action.id"
              type="button"
              :disabled="!canSend || busy"
              @click="handleAction(action)"
            >
              {{ action.label }}
            </button>
          </div>
        </article>
      </div>
    </section>

    <section class="reader-panel">
      <template v-if="activeChapter">
        <p class="eyebrow">{{ activeChapter.meta.book_title }}</p>
        <h2>{{ activeChapter.meta.chapter_no }}. {{ activeChapter.meta.chapter_title }}</h2>
        <p class="muted">第 {{ activeChapter.meta.section_no }}/{{ activeChapter.meta.section_count }} 节</p>
        <p v-if="activeChapter.meta.summary" class="summary">{{ activeChapter.meta.summary }}</p>
        <article class="chapter-body">{{ activeChapter.body }}</article>
      </template>
      <template v-else>
        <h2>选择一个阅读动作开始</h2>
        <p class="muted">首版界面只提供按钮选择，不提供自由聊天输入。</p>
        <p class="muted">当前已发现 {{ chapters.length }} 个阅读单元。</p>
      </template>
    </section>
  </main>
</template>