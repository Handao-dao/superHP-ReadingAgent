<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { listChapters } from './api/chapters'
import { lookupWord } from './api/lookup'
import { addVocabulary, setMasteredByWord } from './api/vocabulary'
import VocabularyPanel from './components/VocabularyPanel.vue'
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
const sidebarOpen = ref(false)
const activeView = ref('reader')
const vocabularyRefreshKey = ref(0)
const manualAnnotations = ref(new Map())
const hiddenAnnotations = ref(new Set())
const lookupVisible = ref(false)
const lookupLoading = ref(false)
const lookupSaving = ref(false)
const lookupError = ref('')
const lookupWordText = ref('')
const lookupSentence = ref('')
const lookupIsAnnotated = ref(false)
const lookupTranslation = ref('')
const lookupResult = ref(null)
const lookupStyle = ref({})

const {
  activeChapter,
  busy,
  canSend,
  cards,
  cardsRevision,
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

const chaptersByBook = computed(() => {
  const groups = new Map()
  for (const chapter of chapters.value) {
    const key = chapter.book_id
    if (!groups.has(key)) {
      groups.set(key, {
        id: key,
        title: chapter.book_title,
        chapters: [],
      })
    }
    groups.get(key).chapters.push(chapter)
  }
  return Array.from(groups.values()).map((group) => ({
    ...group,
    chapters: group.chapters.slice().sort((a, b) => a.chapter_no - b.chapter_no),
  }))
})

const paragraphs = computed(() => {
  const body = activeChapter.value?.body || ''
  return splitReadingBlocks(body)
})

const renderedBlocks = computed(() => paragraphs.value.map((block) => renderReadingBlock(block, {
  manualAnnotations: manualAnnotations.value,
  hiddenAnnotations: hiddenAnnotations.value,
})))
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

const currentTitle = computed(() => {
  const meta = currentMeta.value
  if (!meta) return ''
  return `${meta.chapter_no}. ${meta.chapter_title}`
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

function handleSelectChapter(chapter) {
  if (isGenerating.value) return
  activeView.value = 'reader'
  currentPage.value = 0
  totalReadingPages.value = 0
  completeCardsRequestedFor.value = ''
  closeLookupBubble()
  const sent = requestCards('start', chapter.id)
  if (sent) sidebarOpen.value = false
}

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function nextPage() {
  if (canGoNext.value) currentPage.value += 1
}

function prevPage() {
  if (canGoPrev.value) currentPage.value -= 1
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    closeLookupBubble()
    return
  }
  if (activeView.value !== 'reader') return
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

function normalizeWord(word = '') {
  return String(word).trim().toLowerCase()
}

function cleanWord(word = '') {
  return String(word).replace(/^[^A-Za-z]+|[^A-Za-z]+$/g, '')
}

function stripAnnotationMarkers(text = '') {
  return String(text).replace(/\[\[(.+?)\|.+?\]\]/g, '$1')
}

function calcLookupStyle(target) {
  const rect = target.getBoundingClientRect()
  const width = 320
  const left = Math.min(window.innerWidth - width - 16, Math.max(16, rect.left + rect.width / 2 - width / 2))
  const top = Math.min(window.innerHeight - 260, rect.bottom + 12)
  return {
    left: `${left}px`,
    top: `${Math.max(16, top)}px`,
    width: `${width}px`,
  }
}

function extractSentence(target) {
  const block = target.closest('.reading-block')
  const text = stripAnnotationMarkers(block?.innerText || target.textContent || '')
    .replace(/\([^()]{1,16}\)/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!text) return ''
  const word = cleanWord(target.dataset.word || target.textContent || '').toLowerCase()
  const parts = text.match(/[^.!?。！？]+[.!?。！？]?/g) || [text]
  return (parts.find((part) => part.toLowerCase().includes(word)) || text).trim()
}

function closeLookupBubble() {
  lookupVisible.value = false
  lookupLoading.value = false
  lookupSaving.value = false
  lookupError.value = ''
  lookupResult.value = null
}

async function handleReadingClick(event) {
  const target = event.target.closest?.('[data-word]')
  if (!target || !readingFlow.value?.contains(target)) {
    closeLookupBubble()
    return
  }

  const word = cleanWord(target.dataset.word || target.textContent || '')
  if (!word) return

  lookupVisible.value = true
  lookupLoading.value = true
  lookupSaving.value = false
  lookupError.value = ''
  lookupWordText.value = word
  lookupSentence.value = extractSentence(target)
  lookupIsAnnotated.value = target.classList.contains('vocab-word')
  lookupTranslation.value = target.dataset.translation || ''
  lookupResult.value = null
  lookupStyle.value = calcLookupStyle(target)

  try {
    const result = await lookupWord(word, lookupSentence.value)
    if (!result.word_cn && lookupTranslation.value) result.word_cn = lookupTranslation.value
    lookupResult.value = result
  } catch (error) {
    lookupError.value = error.message || '查词失败'
    if (lookupTranslation.value) {
      lookupResult.value = {
        word,
        word_cn: lookupTranslation.value,
        sentence_cn: '',
      }
    }
  } finally {
    lookupLoading.value = false
  }
}

async function addLookupAnnotation() {
  const translation = lookupResult.value?.word_cn || lookupTranslation.value
  const unitId = activeChapter.value?.meta?.id || currentChapterId.value
  if (!unitId || !lookupWordText.value || !translation) return
  lookupSaving.value = true
  lookupError.value = ''
  try {
    await addVocabulary({
      word: lookupWordText.value,
      translation,
      context: lookupSentence.value,
      unitId,
    })
    const key = normalizeWord(lookupWordText.value)
    const nextManual = new Map(manualAnnotations.value)
    const nextHidden = new Set(hiddenAnnotations.value)
    nextManual.set(key, translation)
    nextHidden.delete(key)
    manualAnnotations.value = nextManual
    hiddenAnnotations.value = nextHidden
    lookupIsAnnotated.value = true
    vocabularyRefreshKey.value += 1
    loadChapterList()
    await recalculatePages()
  } catch (error) {
    lookupError.value = error.message || '添加标注失败'
  } finally {
    lookupSaving.value = false
  }
}

async function hideLookupAnnotation() {
  if (!lookupWordText.value) return
  lookupSaving.value = true
  lookupError.value = ''
  const key = normalizeWord(lookupWordText.value)
  try {
    await setMasteredByWord(lookupWordText.value, true)
    const nextManual = new Map(manualAnnotations.value)
    const nextHidden = new Set(hiddenAnnotations.value)
    nextManual.delete(key)
    nextHidden.add(key)
    manualAnnotations.value = nextManual
    hiddenAnnotations.value = nextHidden
    lookupIsAnnotated.value = false
    vocabularyRefreshKey.value += 1
    loadChapterList()
    closeLookupBubble()
    await recalculatePages()
  } catch (error) {
    lookupError.value = error.message || '取消标注失败'
  } finally {
    lookupSaving.value = false
  }
}

function handleVocabularyChanged() {
  vocabularyRefreshKey.value += 1
  loadChapterList()
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
    manualAnnotations.value = new Map()
    hiddenAnnotations.value = new Set()
    closeLookupBubble()
    recalculatePages()
  }
)

watch(() => activeChapter.value?.body, recalculatePages)
watch([manualAnnotations, hiddenAnnotations], recalculatePages)

watch(cardsRevision, () => {
  loadChapterList()
})

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
  <main class="reader-layout" :class="{ 'is-sidebar-open': sidebarOpen }">
    <aside class="chapter-sidebar" aria-label="章节目录">
      <div class="sidebar-header">
        <p class="eyebrow">Library</p>
        <h2>目录</h2>
      </div>

      <div v-if="listErrorMessage" class="sidebar-error">{{ listErrorMessage }}</div>
      <div v-else-if="listLoading" class="sidebar-loading">正在读取目录...</div>

      <nav v-else class="book-list">
        <section v-for="book in chaptersByBook" :key="book.id" class="book-group">
          <h3>{{ book.title }}</h3>
          <button
            v-for="chapter in book.chapters"
            :key="chapter.id"
            type="button"
            class="chapter-item"
            :class="{ 'is-active': chapter.id === currentChapterId, 'is-read': chapter.status === 'read' }"
            :disabled="isGenerating"
            @click="handleSelectChapter(chapter)"
          >
            <span class="chapter-number">{{ chapter.chapter_no }}</span>
            <span class="chapter-main">
              <span class="chapter-title">{{ chapter.chapter_title }}</span>
              <span class="chapter-badges">
                <span v-if="chapter.status === 'read'">已读</span>
                <span v-if="chapter.has_annotated_copy">译注</span>
                <span v-if="chapter.vocab_count > 0">{{ chapter.vocab_count }} 词</span>
              </span>
            </span>
          </button>
        </section>
      </nav>
    </aside>

    <button
      type="button"
      class="sidebar-scrim"
      aria-label="关闭目录"
      @click="sidebarOpen = false"
    ></button>

    <section class="reader-shell">
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
        <div class="view-switch" aria-label="页面切换">
          <button type="button" :class="{ 'is-active': activeView === 'reader' }" @click="activeView = 'reader'">阅读</button>
          <button type="button" :class="{ 'is-active': activeView === 'vocabulary' }" @click="activeView = 'vocabulary'">生词表</button>
        </div>
        <button type="button" class="catalog-toggle" @click="toggleSidebar">目录</button>
        <span class="status-pill" :class="{ 'is-online': connected }">{{ connected ? '在线' : '离线' }}</span>
        <span class="page-chip">{{ pageLabel }}</span>
      </div>
      </header>

      <section v-if="activeView === 'reader'" class="book-stage">
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
              <div ref="readingFlow" class="reading-flow" :style="flowTransform" @click="handleReadingClick">
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

        <aside v-if="lookupVisible" class="lookup-bubble" :style="lookupStyle">
          <div class="lookup-head">
            <div>
              <p class="small-label">Lookup</p>
              <h3>{{ lookupWordText }}</h3>
            </div>
            <button type="button" class="icon-button" aria-label="关闭查词" @click="closeLookupBubble">×</button>
          </div>

          <p v-if="lookupLoading" class="lookup-muted">正在查词...</p>
          <p v-else-if="lookupError" class="lookup-error">{{ lookupError }}</p>

          <template v-if="lookupResult">
            <p class="lookup-translation">{{ lookupResult.word_cn || lookupTranslation || '暂无译文' }}</p>
            <p v-if="lookupSentence" class="lookup-sentence">{{ lookupSentence }}</p>
            <p v-if="lookupResult.sentence_cn" class="lookup-sentence-cn">{{ lookupResult.sentence_cn }}</p>
          </template>

          <div class="lookup-actions">
            <button
              v-if="!lookupIsAnnotated"
              type="button"
              :disabled="lookupLoading || lookupSaving || !(lookupResult?.word_cn || lookupTranslation)"
              @click="addLookupAnnotation"
            >添加标注</button>
            <button
              v-else
              type="button"
              :disabled="lookupSaving"
              @click="hideLookupAnnotation"
            >取消标注</button>
          </div>
        </aside>

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

      <section v-else class="book-stage vocabulary-stage">
        <article class="paper-surface vocabulary-surface">
          <VocabularyPanel
            :current-unit-id="currentChapterId"
            :current-title="currentTitle"
            :refresh-key="vocabularyRefreshKey"
            @changed="handleVocabularyChanged"
          />
        </article>
      </section>
    </section>
  </main>
</template>
