<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { listChapters } from './api/chapters'
import { useReadingSocket } from './composables/useReadingSocket'
import { renderReadingBlock, splitReadingBlocks } from './utils/renderReadingText'

const chapters = ref([])
const listLoading = ref(false)
const listErrorMessage = ref('')
const currentPage = ref(0)
const completeCardsRequestedFor = ref('')
const readingViewport = ref(null)
const readingFlow = ref(null)
const pageStride = ref(0)
const totalReadingPages = ref(0)

const {
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
  requestCards,
  statusMessage,
  connect,
  sendAction,
} = useReadingSocket()

const activeMeta = computed(() => activeChapter.value?.meta || null)
const currentMeta = computed(() => {
  if (activeMeta.value) return activeMeta.value
  if (!currentChapterId.value) return null
  return chapters.value.find((unit) => unit.id === currentChapterId.value) || null
})

const paragraphs = computed(() => {
  const body = activeChapter.value?.body || ''
  return splitReadingBlocks(body)
})

const renderedBlocks = computed(() => paragraphs.value.map((block) => renderReadingBlock(block)))
const hasActiveReading = computed(() => Boolean(activeChapter.value && renderedBlocks.value.length > 0))
const isGuidancePage = computed(() => hasActiveReading.value && totalReadingPages.value > 0 && currentPage.value >= totalReadingPages.value)
const flowTransform = computed(() => ({
  transform: `translateX(-${currentPage.value * pageStride.value}px)`,
}))
const canGoPrev = computed(() => currentPage.value > 0)
const canGoNext = computed(() => hasActiveReading.value && totalReadingPages.value > 0 && currentPage.value < totalReadingPages.value)

const isGenerating = computed(() => {
  return ['generating_annotation', 'model_retrying', 'json_repairing'].includes(loadStatus.value)
})

const readerMode = computed(() => {
  if (isGenerating.value) return 'generating'
  if (errorMessage.value && !hasActiveReading.value) return 'error'
  if (isGuidancePage.value || (!hasActiveReading.value && cards.value.length > 0)) return 'guidance'
  if (hasActiveReading.value) return 'reading'
  return 'empty'
})

const pageLabel = computed(() => {
  if (!hasActiveReading.value) return '未开始'
  if (totalReadingPages.value <= 0) return '排版中'
  if (isGuidancePage.value) return '引导页'
  return `${currentPage.value + 1} / ${totalReadingPages.value}`
})

const chapterLabel = computed(() => {
  const meta = currentMeta.value
  if (!meta) return '等待阅读单元'
  return `第 ${meta.chapter_no} 章`
})

const summaryText = computed(() => {
  return currentMeta.value?.summary || cards.value[0]?.body || '阅读助手正在准备下一步。'
})

const surfaceTone = computed(() => ({
  'is-guidance': readerMode.value === 'guidance',
  'is-generating': readerMode.value === 'generating',
  'is-error': readerMode.value === 'error',
}))

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

function nextPage() {
  if (canGoNext.value) currentPage.value += 1
}

function prevPage() {
  if (canGoPrev.value) currentPage.value -= 1
}

function handleKeydown(event) {
  if (isGenerating.value) return
  if (event.key === 'ArrowRight' || event.key === ' ') {
    event.preventDefault()
    nextPage()
  }
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    prevPage()
  }
}

async function recalculatePages() {
  await nextTick()
  if (document.fonts?.ready) await document.fonts.ready
  await new Promise((resolve) => requestAnimationFrame(resolve))

  const viewport = readingViewport.value
  const flow = readingFlow.value
  if (!viewport || !flow || !renderedBlocks.value.length) {
    totalReadingPages.value = 0
    pageStride.value = 0
    return
  }

  const styles = window.getComputedStyle(flow)
  const gap = Number.parseFloat(styles.columnGap) || 0
  const viewportWidth = viewport.clientWidth
  pageStride.value = viewportWidth + gap
  flow.style.setProperty('--reader-column-width', `${viewportWidth}px`)
  flow.style.setProperty('--reader-column-gap', `${gap}px`)

  await new Promise((resolve) => requestAnimationFrame(resolve))
  const pages = Math.max(1, Math.ceil((flow.scrollWidth + 1) / Math.max(1, pageStride.value)))
  totalReadingPages.value = pages
  if (currentPage.value > pages) currentPage.value = pages
}

watch(
  () => activeChapter.value?.meta?.id + activeChapter.value?.body_kind,
  () => {
    currentPage.value = 0
    totalReadingPages.value = 0
    completeCardsRequestedFor.value = ''
    recalculatePages()
  }
)

watch(() => activeChapter.value?.body, recalculatePages)

watch(isGuidancePage, (isGuidance) => {
  const unitId = activeChapter.value?.meta?.id
  if (!isGuidance || !unitId || completeCardsRequestedFor.value === unitId) return
  completeCardsRequestedFor.value = unitId
  requestCards('complete')
})

onMounted(() => {
  loadChapterList()
  connect()
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('resize', recalculatePages)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', recalculatePages)
})
</script>

<template>
  <main class="reader-shell">
    <header class="reader-topbar">
      <div class="title-block">
        <p class="eyebrow">SuperHP Agent</p>
        <h1>{{ currentMeta?.book_title || '章节阅读助手' }}</h1>
        <p class="chapter-line">
          <span>{{ currentMeta ? `${currentMeta.chapter_no}. ${currentMeta.chapter_title}` : '选择一个阅读动作开始' }}</span>
          <span>{{ chapterLabel }}</span>
        </p>
      </div>

      <div class="session-cluster">
        <span class="status-pill" :class="{ 'is-online': connected }">{{ connected ? '在线' : '离线' }}</span>
        <span class="page-chip">{{ pageLabel }}</span>
      </div>
    </header>

    <section class="book-stage">
      <button
        type="button"
        class="page-turn page-turn-left"
        :disabled="!canGoPrev || isGenerating"
        aria-label="上一页"
        @click="prevPage"
      >‹</button>

      <article class="paper-surface" :class="surfaceTone">
        <div class="paper-status">
          <span>{{ progressMessage || noticeMessage || statusMessage }}</span>
          <span v-if="listLoading">正在读取目录...</span>
          <span v-if="listErrorMessage" class="inline-error">{{ listErrorMessage }}</span>
        </div>

        <div v-if="errorMessage" class="paper-alert" role="status">
          {{ errorMessage }}
        </div>

        <template v-if="readerMode === 'generating'">
          <div class="summary-page">
            <p class="small-label">{{ progressMessage || noticeMessage || '正在生成译注...' }}</p>
            <h2>本章概要</h2>
            <p>{{ summaryText }}</p>
          </div>
        </template>

        <template v-else-if="readerMode === 'reading'">
          <div class="reading-page" :class="{ 'is-annotated': activeChapter?.body_kind === 'annotated' }">
            <div ref="readingViewport" class="reading-viewport">
              <div ref="readingFlow" class="reading-flow" :style="flowTransform">
                <div
                  v-for="(html, index) in renderedBlocks"
                  :key="index"
                  class="reading-block"
                  v-html="html"
                ></div>
              </div>
            </div>
          </div>
        </template>

        <template v-else-if="readerMode === 'guidance'">
          <div class="guidance-page">
            <p class="small-label">阅读引导</p>
            <h2>{{ hasActiveReading ? '这一章读完了，下一步呢？' : '准备开始阅读' }}</h2>
            <p class="guidance-summary">{{ summaryText }}</p>

            <div class="guide-card-list">
              <article v-for="card in cards" :key="card.id" class="guide-card">
                <p class="card-type">{{ card.type }}</p>
                <h3>{{ card.title }}</h3>
                <p>{{ card.body }}</p>
                <div class="actions">
                  <button
                    v-for="action in card.actions"
                    :key="`${card.id}-${action.id}`"
                    type="button"
                    :disabled="!canSend || busy"
                    @click="handleAction(action)"
                  >{{ action.label }}</button>
                </div>
              </article>
            </div>
          </div>
        </template>

        <template v-else-if="readerMode === 'error'">
          <div class="summary-page error-state">
            <p class="small-label">阅读会话遇到问题</p>
            <h2>暂时无法继续</h2>
            <p>{{ errorMessage || listErrorMessage }}</p>
          </div>
        </template>

        <template v-else>
          <div class="summary-page empty-state">
            <p class="small-label">等待开始</p>
            <h2>选择一个阅读动作开始</h2>
            <p>首版界面只提供按钮选择，不提供自由聊天输入。当前已发现 {{ chapters.length }} 个阅读单元。</p>
          </div>
        </template>

        <footer class="paper-footer">
          <span>{{ activeChapter?.body_kind === 'annotated' ? '译注副本' : '原文阅读' }}</span>
          <span>{{ pageLabel }}</span>
        </footer>
      </article>

      <button
        type="button"
        class="page-turn page-turn-right"
        :disabled="!canGoNext || isGenerating"
        aria-label="下一页"
        @click="nextPage"
      >›</button>
    </section>
  </main>
</template>
