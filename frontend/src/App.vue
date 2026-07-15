<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import VocabularyPanel from './components/VocabularyPanel.vue'
import GuidancePanel from './components/reading/GuidancePanel.vue'
import LookupPopover from './components/reading/LookupPopover.vue'
import ReaderStatePage from './components/reading/ReaderStatePage.vue'
import ReadingPaperFooter from './components/reading/ReadingPaperFooter.vue'
import ReadingSidebar from './components/reading/ReadingSidebar.vue'
import ReadingTextPage from './components/reading/ReadingTextPage.vue'
import ReadingTopbar from './components/reading/ReadingTopbar.vue'
import { useBookmarks } from './composables/useBookmarks'
import { useReaderPagination } from './composables/useReaderPagination'
import { useReadingCatalog } from './composables/useReadingCatalog'
import { useReadingSocket } from './composables/useReadingSocket'
import { useWordLookup } from './composables/useWordLookup'
import { getReadingRenderer } from './renderers'

const PAPER_THEME_STORAGE_KEY = 'superhp_reader_theme'
const PAPER_THEMES = new Set(['parchment', 'white-paper'])

const completeCardsRequestedFor = ref('')
const sidebarOpen = ref(false)
const storedPaperTheme = localStorage.getItem(PAPER_THEME_STORAGE_KEY)
const paperTheme = ref(PAPER_THEMES.has(storedPaperTheme) ? storedPaperTheme : 'parchment')
const paperThemeOpen = ref(false)
const activeView = ref('reader')
const vocabularyRefreshKey = ref(0)
const selectedVocabularyUnitId = ref('')
const {
  catalogErrorMessage,
  chapters,
  currentProfile,
  libraryCollections,
  listErrorMessage,
  listLoading,
  loadChapterCatalog,
  loadLibraryCatalog,
  loadProfileList,
  profileErrorMessage,
  profileOptions,
  selectedProfileId,
} = useReadingCatalog()

const {
  activeChapter,
  annotationWarning,
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
} = useReadingSocket({ profileId: selectedProfileId })

const activeMeta = computed(() => activeChapter.value?.meta || null)
const currentMeta = computed(() => {
  if (activeMeta.value?.profile_id === selectedProfileId.value) return activeMeta.value
  if (!currentChapterId.value) return null
  return chapters.value.find((unit) => unit.id === currentChapterId.value) || null
})
const currentRenderer = computed(() => getReadingRenderer(currentMeta.value?.profile_id || selectedProfileId.value))
const profileShellClass = computed(() => `profile-${selectedProfileId.value}`)

const {
  addLookupAnnotation,
  closeLookupBubble,
  handleReadingClick,
  hiddenAnnotations,
  hideLookupAnnotation,
  lookupError,
  lookupIsAnnotated,
  lookupLoading,
  lookupResult,
  lookupSaving,
  lookupSentence,
  lookupStyle,
  lookupTranslation,
  lookupVisible,
  lookupWordText,
  loadLookupAnnotations,
  manualAnnotations,
  resetLookupAnnotations,
  stripAnnotationMarkers,
} = useWordLookup({
  getProfileId: () => currentMeta.value?.profile_id || selectedProfileId.value,
  getReadingFlow: () => readingFlow.value,
  getUnitId: () => activeChapter.value?.meta?.id || currentChapterId.value,
  onVocabularyChanged: handleLookupVocabularyChanged,
})

const paragraphs = computed(() => {
  const body = activeChapter.value?.body || ''
  return currentRenderer.value.splitReadingBlocks(body)
})

const renderedBlocks = computed(() => paragraphs.value.map((block) => currentRenderer.value.renderReadingBlock(block, {
  manualAnnotations: manualAnnotations.value,
  hiddenAnnotations: hiddenAnnotations.value,
})))
const hasActiveReading = computed(() => Boolean(activeChapter.value && renderedBlocks.value.length > 0))
const {
  canGoNext,
  canGoPrev,
  currentParagraphIndex,
  currentPage,
  flowTransform,
  isGuidancePage,
  nextPage,
  pageForParagraph,
  prevPage,
  readingFlow,
  readingViewport,
  recalculatePages,
  resetPagination,
  totalReadingPages,
} = useReaderPagination({
  hasActiveReading,
  renderedBlocks,
  onLayout: applyPendingBookmarkJump,
})

const isGenerating = computed(() => {
  return ['generating_annotation', 'model_retrying'].includes(loadStatus.value)
})

const readerMode = computed(() => {
  if (isGenerating.value) return 'generating'
  if (errorMessage.value && !hasActiveReading.value) return 'error'
  if (isGuidancePage.value || (!hasActiveReading.value && cards.value.length > 0)) return 'guidance'
  if (hasActiveReading.value) return 'reading'
  return 'empty'
})

const {
  bookmarkError,
  bookmarksByUnit,
  bookmarksLoading,
  bookmarkSaving,
  deleteBookmarkEntry: handleDeleteBookmark,
  deletingBookmarkId,
  loadBookmarks,
  queueBookmarkJump,
  resolvePendingBookmarkJump,
  saveCurrentBookmark,
} = useBookmarks({
  getActiveChapter: () => activeChapter.value,
  getCurrentPage: () => currentPage.value,
  getCurrentParagraphIndex: currentParagraphIndex,
  getPageForParagraph: pageForParagraph,
  getParagraphs: () => paragraphs.value,
  getReaderMode: () => readerMode.value,
  getTotalPages: () => totalReadingPages.value,
  stripAnnotationMarkers,
})

const pageLabel = computed(() => {
  if (!hasActiveReading.value) return '未开始'
  if (totalReadingPages.value <= 0) return '排版中'
  if (isGuidancePage.value) return '引导页'
  return `${currentPage.value + 1} / ${totalReadingPages.value}`
})

const paperPageLabel = computed(() => {
  if (!hasActiveReading.value) return 'Not started'
  if (totalReadingPages.value <= 0) return 'Laying out'
  if (isGuidancePage.value) return 'Guide'
  return `${currentPage.value + 1} / ${totalReadingPages.value}`
})

const chapterLabel = computed(() => {
  const meta = currentMeta.value
  if (!meta) return 'Waiting for unit'
  if (meta.profile_id === 'classical_chinese') return `第 ${meta.chapter_no} 篇 ${meta.chapter_title}`
  return `Chapter ${meta.chapter_no} ${meta.chapter_title}`
})

const summaryText = computed(() => {
  return currentMeta.value?.summary || cards.value[0]?.body || 'The reading assistant is preparing the next step.'
})

const currentTitle = computed(() => {
  const meta = currentMeta.value
  if (!meta) return ''
  return `${meta.chapter_no}. ${meta.chapter_title}`
})

const chapterDetailText = computed(() => {
  const meta = currentMeta.value
  if (!meta) return ''
  if (meta.profile_id === 'classical_chinese') return `第 ${meta.chapter_no} 篇 · ${meta.chapter_title}`
  return `Chapter ${meta.chapter_no} · ${meta.chapter_title}`
})

const guideActionTitle = computed(() => (hasActiveReading.value ? 'Next Step' : 'Reading Mode'))

const surfaceTone = computed(() => ({
  'is-guidance': readerMode.value === 'guidance',
  'is-generating': readerMode.value === 'generating',
  'is-error': readerMode.value === 'error',
}))

async function loadChapterList() {
  const loaded = await loadChapterCatalog()
  if (loaded && currentChapterId.value && !loaded.some((unit) => unit.id === currentChapterId.value)) {
    currentChapterId.value = null
  }
}

function handleAction(action) {
  if (action.id === 'review_chapter_vocab') {
    selectedVocabularyUnitId.value = action.payload?.unit_id || action.payload?.chapter_id || currentChapterId.value || ''
    activeView.value = 'vocabulary'
    closeLookupBubble()
    return
  }
  const actionUnitId = action.payload?.unit_id || action.payload?.chapter_id
  if (actionUnitId) currentChapterId.value = actionUnitId
  sendAction(action)
}

function handleSelectChapter(chapter) {
  if (isGenerating.value) return
  activeView.value = 'reader'
  resetPagination()
  completeCardsRequestedFor.value = ''
  closeLookupBubble()
  const sent = requestCards('start', chapter.id)
  if (sent) sidebarOpen.value = false
}

async function handleSelectProfile(profileId) {
  if (isGenerating.value || profileId === selectedProfileId.value) return
  selectedProfileId.value = profileId
  activeView.value = 'reader'
  activeChapter.value = null
  cards.value = []
  currentChapterId.value = null
  resetPagination()
  completeCardsRequestedFor.value = ''
  selectedVocabularyUnitId.value = ''
  closeLookupBubble()
  await loadChapterList()
  requestCards('start', '')
}

function handleOpenBookmark(bookmark) {
  if (isGenerating.value) return
  activeView.value = 'reader'
  closeLookupBubble()
  queueBookmarkJump(bookmark)
  currentChapterId.value = bookmark.unit_id
  const action = {
    id: bookmark.body_kind === 'annotated' ? 'open_annotated_copy' : 'read_original',
    label: bookmark.body_kind === 'annotated' ? 'Annotated' : 'Original',
    payload: {
      unit_id: bookmark.unit_id,
      chapter_id: bookmark.unit_id,
    },
  }
  sendAction(action)
  sidebarOpen.value = false
}

function applyPendingBookmarkJump() {
  const targetPage = resolvePendingBookmarkJump({
    activeUnitId: activeChapter.value?.meta?.id,
    bodyKind: activeChapter.value?.body_kind,
    totalPages: totalReadingPages.value,
  })
  if (targetPage !== null) currentPage.value = targetPage
}

function handleReadingElements({ flow, viewport }) {
  readingFlow.value = flow
  readingViewport.value = viewport
  if (flow && viewport) recalculatePages()
}

function toggleSidebar() {
  paperThemeOpen.value = false
  sidebarOpen.value = !sidebarOpen.value
}

function selectPaperTheme(theme) {
  if (!PAPER_THEMES.has(theme)) return
  paperTheme.value = theme
  paperThemeOpen.value = false
  localStorage.setItem(PAPER_THEME_STORAGE_KEY, theme)
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    closeLookupBubble()
    paperThemeOpen.value = false
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

async function handleVocabularyChanged() {
  vocabularyRefreshKey.value += 1
  await loadChapterList()
}

async function handleLookupVocabularyChanged() {
  await handleVocabularyChanged()
  await recalculatePages()
}

watch(
  () => activeChapter.value?.meta?.id + activeChapter.value?.body_kind,
  async () => {
    resetPagination()
    completeCardsRequestedFor.value = ''
    resetLookupAnnotations()
    closeLookupBubble()
    recalculatePages()
    const unitId = activeChapter.value?.meta?.id
    if (unitId) {
      await loadLookupAnnotations(unitId)
      await recalculatePages()
    }
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
  loadProfileList()
  loadLibraryCatalog()
  loadChapterList()
  loadBookmarks()
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
  <main
    class="reader-layout"
    :class="[{ 'is-sidebar-open': sidebarOpen }, profileShellClass]"
    :data-reader-theme="paperTheme"
    @click="paperThemeOpen = false"
  >
    <ReadingSidebar
      :bookmark-error="bookmarkError"
      :bookmarks-by-unit="bookmarksByUnit"
      :bookmarks-loading="bookmarksLoading"
      :catalog-error="catalogErrorMessage"
      :collections="libraryCollections"
      :current-chapter-id="currentChapterId || ''"
      :deleting-bookmark-id="deletingBookmarkId"
      :is-generating="isGenerating"
      :list-error="listErrorMessage"
      :list-loading="listLoading"
      :profile-error="profileErrorMessage"
      :profile-options="profileOptions"
      :selected-profile-id="selectedProfileId"
      @close="sidebarOpen = false"
      @delete-bookmark="handleDeleteBookmark"
      @open-bookmark="handleOpenBookmark"
      @select-chapter="handleSelectChapter"
      @select-profile="handleSelectProfile"
    />

    <section class="reader-shell">
      <ReadingTopbar
        :active-view="activeView"
        :book-title="currentMeta?.book_title || currentProfile.label"
        :chapter-label="currentMeta ? chapterLabel : ''"
        :connected="connected"
        :page-label="pageLabel"
        :paper-theme="paperTheme"
        :paper-theme-open="paperThemeOpen"
        @paper-theme-change="selectPaperTheme"
        @toggle-paper-theme="paperThemeOpen = !paperThemeOpen"
        @toggle-sidebar="toggleSidebar"
        @view-change="activeView = $event"
      />

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

        <div v-else-if="annotationWarning" class="paper-alert paper-alert-warning" role="status">
          {{ annotationWarning }}
        </div>

        <template v-if="readerMode === 'reading'">
          <ReadingTextPage
            :annotated="activeChapter?.body_kind === 'annotated'"
            :blocks="renderedBlocks"
            :flow-transform="flowTransform"
            @elements-change="handleReadingElements"
            @reading-click="handleReadingClick"
          />
        </template>

        <template v-else-if="readerMode === 'guidance'">
          <GuidancePanel
            :busy="busy"
            :can-send="canSend"
            :cards="cards"
            :chapter-detail="chapterDetailText"
            :current-meta="currentMeta"
            :has-active-reading="hasActiveReading"
            :summary="summaryText"
            :title="guideActionTitle"
            @action="handleAction"
          />
        </template>

        <ReaderStatePage
          v-else
          :error-message="errorMessage || listErrorMessage"
          :mode="readerMode"
          :profile-label="currentProfile.label"
          :progress-text="progressMessage || noticeMessage"
          :summary="summaryText"
          :unit-count="chapters.length"
        />

        <LookupPopover
          :error="lookupError"
          :is-annotated="lookupIsAnnotated"
          :loading="lookupLoading"
          :result="lookupResult"
          :saving="lookupSaving"
          :sentence="lookupSentence"
          :style="lookupStyle"
          :translation="lookupTranslation"
          :visible="lookupVisible"
          :word="lookupWordText"
          @add="addLookupAnnotation"
          @close="closeLookupBubble"
          @remove="hideLookupAnnotation"
        />

        <ReadingPaperFooter
          :body-kind="activeChapter?.body_kind || ''"
          :page-label="paperPageLabel"
          :reader-mode="readerMode"
          :saving-bookmark="bookmarkSaving"
          @save-bookmark="saveCurrentBookmark"
        />
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
            :collections="libraryCollections"
            :current-unit-id="currentChapterId"
            :current-title="currentTitle"
            :profile-id="selectedProfileId"
            :refresh-key="vocabularyRefreshKey"
            v-model:selected-unit-id="selectedVocabularyUnitId"
            @changed="handleVocabularyChanged"
          />
        </article>
      </section>
    </section>
  </main>
</template>
