<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import VocabularyPanel from './components/VocabularyPanel.vue'
import GuidancePanel from './components/reading/GuidancePanel.vue'
import LookupPopover from './components/reading/LookupPopover.vue'
import ReadingTopbar from './components/reading/ReadingTopbar.vue'
import { useBookmarks } from './composables/useBookmarks'
import { useReaderPagination } from './composables/useReaderPagination'
import { useReadingCatalog } from './composables/useReadingCatalog'
import { useReadingSocket } from './composables/useReadingSocket'
import { useWordLookup } from './composables/useWordLookup'
import { getReadingRenderer } from './renderers'

const completeCardsRequestedFor = ref('')
const sidebarOpen = ref(false)
const activeView = ref('reader')
const vocabularyRefreshKey = ref(0)
const selectedVocabularyUnitId = ref('')
const densityOptions = [
  { key: 'H', label: 'High', level: 'beginner' },
  { key: 'M', label: 'Medium', level: 'intermediate' },
  { key: 'L', label: 'Low', level: 'advanced' },
]
const selectedDensity = ref(localStorage.getItem('superhp_annotation_density') || 'M')
if (!densityOptions.some((option) => option.key === selectedDensity.value)) {
  selectedDensity.value = 'M'
}
const {
  chapters,
  chaptersByBook,
  currentProfile,
  listErrorMessage,
  listLoading,
  loadChapterCatalog,
  loadProfileList,
  profileErrorMessage,
  profileOptions,
  selectedProfileId,
} = useReadingCatalog()

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
  currentPage,
  flowTransform,
  isGuidancePage,
  nextPage,
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
  return ['generating_annotation', 'model_retrying', 'json_repairing'].includes(loadStatus.value)
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
  formatBookmarkTime,
  loadBookmarks,
  queueBookmarkJump,
  resolvePendingBookmarkJump,
  saveCurrentBookmark,
} = useBookmarks({
  getActiveChapter: () => activeChapter.value,
  getCurrentPage: () => currentPage.value,
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

const selectedLevel = computed(() => {
  return densityOptions.find((option) => option.key === selectedDensity.value)?.level || 'intermediate'
})

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
  const actionWithDensity = ['generate_annotation', 'open_annotated_copy'].includes(action.id)
    ? {
        ...action,
        payload: {
          ...(action.payload || {}),
          level: selectedLevel.value,
        },
      }
    : action
  sendAction(actionWithDensity)
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

function chapterNumberLabel(chapter) {
  if (chapter.profile_id === 'classical_chinese') return String(chapter.chapter_no)
  return String(chapter.chapter_no).padStart(2, '0')
}

function chapterNumberKicker(chapter) {
  return chapter.profile_id === 'classical_chinese' ? '篇' : 'CH'
}

function bookUnitCount(book) {
  const unit = selectedProfileId.value === 'classical_chinese' ? '篇' : 'chapters'
  return `${book.chapters.length} ${unit}`
}

function chapterBadgeText(chapter, type) {
  if (chapter.profile_id === 'classical_chinese') {
    if (type === 'read') return '已读'
    if (type === 'annotated') return '注释'
    if (type === 'vocab') return `${chapter.vocab_count} 重点`
    if (type === 'bookmark') return `${bookmarksByUnit.value.get(chapter.id)?.length || 0} 书签`
  }
  if (type === 'read') return 'Read'
  if (type === 'annotated') return 'Annotated'
  if (type === 'vocab') return `${chapter.vocab_count} words`
  if (type === 'bookmark') return `${bookmarksByUnit.value.get(chapter.id)?.length || 0} marks`
  return ''
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
      ...(bookmark.body_kind === 'annotated' ? { level: selectedLevel.value } : {}),
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

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function selectDensity(key) {
  selectedDensity.value = densityOptions.some((option) => option.key === key) ? key : 'M'
  localStorage.setItem('superhp_annotation_density', selectedDensity.value)
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
  () => {
    resetPagination()
    completeCardsRequestedFor.value = ''
    resetLookupAnnotations()
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
  loadProfileList()
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
  <main class="reader-layout" :class="[{ 'is-sidebar-open': sidebarOpen }, profileShellClass]">
    <aside class="chapter-sidebar" aria-label="章节目录">
      <div class="sidebar-header">
        <p class="eyebrow">Library</p>
        <h2>目录</h2>
        <div class="profile-switch" aria-label="阅读场景">
          <button
            v-for="profile in profileOptions"
            :key="profile.id"
            type="button"
            :class="{ 'is-active': selectedProfileId === profile.id }"
            :disabled="isGenerating"
            @click="handleSelectProfile(profile.id)"
          >
            {{ profile.id === 'classical_chinese' ? '文言文' : '英文小说' }}
          </button>
        </div>
      </div>

      <div v-if="profileErrorMessage" class="sidebar-error">{{ profileErrorMessage }}</div>
      <div v-if="listErrorMessage" class="sidebar-error">{{ listErrorMessage }}</div>
      <div v-else-if="listLoading" class="sidebar-loading">正在读取目录...</div>
      <div v-if="bookmarksLoading" class="sidebar-loading">正在读取书签...</div>
      <div v-if="bookmarkError" class="sidebar-error">{{ bookmarkError }}</div>

      <nav v-if="!listErrorMessage && !listLoading" class="book-list">
        <section v-for="book in chaptersByBook" :key="book.id" class="book-group">
          <div class="book-heading">
            <h3>{{ book.title }}</h3>
            <span>{{ bookUnitCount(book) }}</span>
          </div>
          <div
            v-for="chapter in book.chapters"
            :key="chapter.id"
            class="chapter-entry"
          >
            <button
              type="button"
              class="chapter-item"
              :class="{ 'is-active': chapter.id === currentChapterId, 'is-read': chapter.status === 'read' }"
              :disabled="isGenerating"
              @click="handleSelectChapter(chapter)"
            >
              <span class="chapter-number">
                <span class="chapter-number-kicker">{{ chapterNumberKicker(chapter) }}</span>
                <span class="chapter-number-value">{{ chapterNumberLabel(chapter) }}</span>
              </span>
              <span class="chapter-main">
                <span class="chapter-title">{{ chapter.chapter_title }}</span>
                <span class="chapter-badges">
                  <span v-if="chapter.status === 'read'" class="badge-read">{{ chapterBadgeText(chapter, 'read') }}</span>
                  <span v-if="chapter.has_annotated_copy" class="badge-annotated">{{ chapterBadgeText(chapter, 'annotated') }}</span>
                  <span v-if="chapter.vocab_count > 0" class="badge-vocab">{{ chapterBadgeText(chapter, 'vocab') }}</span>
                  <span v-if="bookmarksByUnit.get(chapter.id)?.length" class="badge-bookmark">{{ chapterBadgeText(chapter, 'bookmark') }}</span>
                </span>
              </span>
            </button>

            <div v-if="bookmarksByUnit.get(chapter.id)?.length" class="bookmark-list">
              <div
                v-for="bookmark in bookmarksByUnit.get(chapter.id)"
                :key="bookmark.id"
                class="bookmark-item"
              >
                <button
                  type="button"
                  class="bookmark-open"
                  :disabled="isGenerating"
                  @click="handleOpenBookmark(bookmark)"
                >
                  <span>{{ bookmark.label || `Page ${bookmark.page_index + 1}` }}</span>
                  <small>{{ bookmark.body_kind === 'annotated' ? 'Annotated' : 'Original' }} · {{ formatBookmarkTime(bookmark.created_at) }}</small>
                  <em v-if="bookmark.excerpt">{{ bookmark.excerpt }}</em>
                </button>
                <button
                  type="button"
                  class="bookmark-delete"
                  :disabled="deletingBookmarkId === bookmark.id"
                  aria-label="删除书签"
                  @click="handleDeleteBookmark(bookmark)"
                >×</button>
              </div>
            </div>
          </div>
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
      <ReadingTopbar
        :active-view="activeView"
        :book-title="currentMeta?.book_title || currentProfile.label"
        :chapter-label="currentMeta ? chapterLabel : ''"
        :connected="connected"
        :density-options="densityOptions"
        :is-generating="isGenerating"
        :page-label="pageLabel"
        :selected-density="selectedDensity"
        @select-density="selectDensity"
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

        <template v-if="readerMode === 'generating'">
          <div class="summary-page">
            <p class="small-label">{{ progressMessage || noticeMessage || 'Generating annotations...' }}</p>
            <h2>Chapter Summary</h2>
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

        <template v-else-if="readerMode === 'error'">
          <div class="summary-page error-state">
            <p class="small-label">Session Error</p>
            <h2>Unable to Continue</h2>
            <p>{{ errorMessage || listErrorMessage }}</p>
          </div>
        </template>

        <template v-else>
          <div class="summary-page empty-state">
            <p class="small-label">Waiting</p>
            <h2>Choose a Reading Action</h2>
            <p>{{ currentProfile.label }}当前有 {{ chapters.length }} 个阅读单元。</p>
          </div>
        </template>

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

        <footer class="paper-footer">
          <span>{{ activeChapter?.body_kind === 'annotated' ? 'Annotated' : 'Original' }}</span>
          <button
            v-if="readerMode === 'reading'"
            type="button"
            class="bookmark-save"
            :disabled="bookmarkSaving"
            @click="saveCurrentBookmark"
          >{{ bookmarkSaving ? 'Saving...' : 'Bookmark' }}</button>
          <span>{{ paperPageLabel }}</span>
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
            :chapters="chapters"
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
