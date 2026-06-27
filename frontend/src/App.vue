<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { addBookmark, deleteBookmark, fetchBookmarks } from './api/bookmarks'
import { listChapters } from './api/chapters'
import { lookupWord } from './api/lookup'
import { listProfiles } from './api/profiles'
import { addVocabulary, setMasteredByWord } from './api/vocabulary'
import VocabularyPanel from './components/VocabularyPanel.vue'
import { useReadingSocket } from './composables/useReadingSocket'
import { getReadingRenderer } from './renderers'

const chapters = ref([])
const profiles = ref([])
const listLoading = ref(false)
const listErrorMessage = ref('')
const profileErrorMessage = ref('')
const selectedProfileId = ref(localStorage.getItem('superhp_profile_id') || 'english_novel')
const currentPage = ref(0)
const completeCardsRequestedFor = ref('')
const readingViewport = ref(null)
const readingFlow = ref(null)
const pageStride = ref(0)
const totalReadingPages = ref(0)
const sidebarOpen = ref(false)
const activeView = ref('reader')
const vocabularyRefreshKey = ref(0)
const selectedVocabularyUnitId = ref('')
const bookmarks = ref([])
const bookmarksLoading = ref(false)
const bookmarkError = ref('')
const bookmarkSaving = ref(false)
const deletingBookmarkId = ref(null)
const pendingBookmarkJump = ref(null)
const densityMenuOpen = ref(false)
const densityMenu = ref(null)
const densityOptions = [
  { key: 'H', label: 'High', level: 'beginner' },
  { key: 'M', label: 'Medium', level: 'intermediate' },
  { key: 'L', label: 'Low', level: 'advanced' },
]
const selectedDensity = ref(localStorage.getItem('superhp_annotation_density') || 'M')
if (!densityOptions.some((option) => option.key === selectedDensity.value)) {
  selectedDensity.value = 'M'
}
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
} = useReadingSocket({ profileId: selectedProfileId })

const activeMeta = computed(() => activeChapter.value?.meta || null)
const currentMeta = computed(() => {
  if (activeMeta.value?.profile_id === selectedProfileId.value) return activeMeta.value
  if (!currentChapterId.value) return null
  return chapters.value.find((unit) => unit.id === currentChapterId.value) || null
})
const currentProfile = computed(() => {
  return profiles.value.find((profile) => profile.id === selectedProfileId.value) || {
    id: selectedProfileId.value,
    label: selectedProfileId.value === 'classical_chinese' ? '文言文阅读' : '英文小说阅读',
    renderer_hint: selectedProfileId.value,
  }
})
const profileOptions = computed(() => {
  if (profiles.value.length > 0) return profiles.value
  return [
    { id: 'english_novel', label: '英文小说阅读' },
    { id: 'classical_chinese', label: '文言文阅读' },
  ]
})
const currentRenderer = computed(() => getReadingRenderer(currentMeta.value?.profile_id || selectedProfileId.value))
const profileShellClass = computed(() => `profile-${selectedProfileId.value}`)

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

const bookmarksByUnit = computed(() => {
  const groups = new Map()
  for (const bookmark of bookmarks.value) {
    if (!groups.has(bookmark.unit_id)) groups.set(bookmark.unit_id, [])
    groups.get(bookmark.unit_id).push(bookmark)
  }
  return groups
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
  listLoading.value = true
  listErrorMessage.value = ''
  try {
    chapters.value = await listChapters(selectedProfileId.value)
    if (currentChapterId.value && !chapters.value.some((unit) => unit.id === currentChapterId.value)) {
      currentChapterId.value = null
    }
  } catch (error) {
    listErrorMessage.value = error.message || '阅读单元列表加载失败'
  } finally {
    listLoading.value = false
  }
}

async function loadProfileList() {
  profileErrorMessage.value = ''
  try {
    const loaded = await listProfiles()
    profiles.value = loaded
    if (!loaded.some((profile) => profile.id === selectedProfileId.value)) {
      selectedProfileId.value = loaded.find((profile) => profile.is_default)?.id || loaded[0]?.id || 'english_novel'
    }
  } catch (error) {
    profileErrorMessage.value = error.message || '阅读场景列表加载失败'
  }
}

async function loadBookmarks() {
  bookmarksLoading.value = true
  bookmarkError.value = ''
  try {
    bookmarks.value = await fetchBookmarks()
  } catch (error) {
    bookmarkError.value = error.message || '书签加载失败'
  } finally {
    bookmarksLoading.value = false
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
  currentPage.value = 0
  totalReadingPages.value = 0
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
  localStorage.setItem('superhp_profile_id', profileId)
  activeView.value = 'reader'
  activeChapter.value = null
  cards.value = []
  currentChapterId.value = null
  currentPage.value = 0
  totalReadingPages.value = 0
  completeCardsRequestedFor.value = ''
  selectedVocabularyUnitId.value = ''
  closeLookupBubble()
  await loadChapterList()
  requestCards('start', '')
}

function cleanBookmarkExcerpt(text = '') {
  return stripAnnotationMarkers(text)
    .replace(/^#{1,6}\s+/, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 120)
}

function currentBookmarkExcerpt() {
  const block = paragraphs.value[Math.min(currentPage.value, Math.max(0, paragraphs.value.length - 1))]
  return cleanBookmarkExcerpt(block || activeChapter.value?.body || '')
}

async function saveCurrentBookmark() {
  const meta = activeChapter.value?.meta
  const bodyKind = activeChapter.value?.body_kind
  if (!meta || !bodyKind || readerMode.value !== 'reading') return
  bookmarkSaving.value = true
  bookmarkError.value = ''
  try {
    const totalPages = Math.max(0, totalReadingPages.value)
    const pageIndex = Math.max(0, currentPage.value)
    const saved = await addBookmark({
      unitId: meta.id,
      bodyKind,
      pageIndex,
      progressRatio: totalPages > 0 ? pageIndex / totalPages : 0,
      totalPages,
      label: `Chapter ${meta.chapter_no} · Page ${pageIndex + 1}`,
      excerpt: currentBookmarkExcerpt(),
    })
    bookmarks.value = [saved, ...bookmarks.value]
  } catch (error) {
    bookmarkError.value = error.message || '保存书签失败'
  } finally {
    bookmarkSaving.value = false
  }
}

function handleOpenBookmark(bookmark) {
  if (isGenerating.value) return
  activeView.value = 'reader'
  closeLookupBubble()
  pendingBookmarkJump.value = bookmark
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

async function handleDeleteBookmark(bookmark) {
  deletingBookmarkId.value = bookmark.id
  bookmarkError.value = ''
  try {
    await deleteBookmark(bookmark.id)
    bookmarks.value = bookmarks.value.filter((item) => item.id !== bookmark.id)
  } catch (error) {
    bookmarkError.value = error.message || '删除书签失败'
  } finally {
    deletingBookmarkId.value = null
  }
}

function applyPendingBookmarkJump() {
  const bookmark = pendingBookmarkJump.value
  if (!bookmark || !activeChapter.value || totalReadingPages.value <= 0) return
  if (bookmark.unit_id !== activeChapter.value.meta?.id) return
  if (bookmark.body_kind !== activeChapter.value.body_kind) return
  const pages = totalReadingPages.value
  const savedPage = Number(bookmark.page_index)
  const ratio = Number(bookmark.progress_ratio)
  const ratioPage = Number.isFinite(ratio) ? Math.round((pages - 1) * Math.min(1, Math.max(0, ratio))) : 0
  const targetPage = Number.isInteger(savedPage) && savedPage >= 0 && savedPage < pages ? savedPage : ratioPage
  currentPage.value = Math.min(pages - 1, Math.max(0, targetPage))
  pendingBookmarkJump.value = null
}

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function toggleDensityMenu() {
  if (isGenerating.value) return
  densityMenuOpen.value = !densityMenuOpen.value
}

function selectDensity(key) {
  selectedDensity.value = densityOptions.some((option) => option.key === key) ? key : 'M'
  localStorage.setItem('superhp_annotation_density', selectedDensity.value)
  densityMenuOpen.value = false
}

function formatBookmarkTime(value = '') {
  if (!value) return ''
  const normalized = String(value).replace(' ', 'T')
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function nextPage() {
  if (canGoNext.value) currentPage.value += 1
}

function prevPage() {
  if (canGoPrev.value) currentPage.value -= 1
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    densityMenuOpen.value = false
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

function handleDocumentPointerdown(event) {
  if (!densityMenuOpen.value) return
  if (densityMenu.value?.contains(event.target)) return
  densityMenuOpen.value = false
}

function normalizeWord(word = '') {
  return String(word).trim().toLowerCase()
}

function cleanWord(word = '') {
  const text = String(word).trim()
  if (/[\u3400-\u9fff]/.test(text)) {
    return text.replace(/^[\s，。！？、；：“”‘’（）《》【】]+|[\s，。！？、；：“”‘’（）《》【】]+$/g, '')
  }
  return text.replace(/^[^A-Za-z]+|[^A-Za-z]+$/g, '')
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
    const result = await lookupWord(word, lookupSentence.value, currentMeta.value?.profile_id || selectedProfileId.value)
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
      pos: lookupResult.value?.pos || 'other',
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
    await setMasteredByWord(lookupWordText.value, true, currentMeta.value?.profile_id || selectedProfileId.value)
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
  const wasGuidance = isGuidancePage.value
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
  if (currentPage.value >= pages) currentPage.value = wasGuidance ? pages : pages - 1
  applyPendingBookmarkJump()
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

watch(selectedProfileId, (profileId) => {
  localStorage.setItem('superhp_profile_id', profileId)
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
  document.addEventListener('pointerdown', handleDocumentPointerdown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', recalculatePages)
  document.removeEventListener('pointerdown', handleDocumentPointerdown)
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
      <header class="reader-topbar">
      <div class="title-block">
        <p class="eyebrow">SuperHP Agent</p>
        <h1>{{ currentMeta?.book_title || currentProfile.label || 'Reading Assistant' }}</h1>
        <p class="chapter-line">
          <span>{{ currentMeta ? chapterLabel : 'Choose a reading action to begin' }}</span>
        </p>
      </div>

      <div class="session-cluster">
        <div class="view-switch" aria-label="页面切换">
          <button type="button" :class="{ 'is-active': activeView === 'reader' }" @click="activeView = 'reader'">阅读</button>
          <button type="button" :class="{ 'is-active': activeView === 'vocabulary' }" @click="activeView = 'vocabulary'">生词表</button>
        </div>
        <div ref="densityMenu" class="density-menu">
          <button
            type="button"
            class="density-trigger"
            :class="{ 'is-open': densityMenuOpen }"
            :disabled="isGenerating"
            aria-haspopup="menu"
            :aria-expanded="densityMenuOpen"
            @click="toggleDensityMenu"
          >
            Density: {{ selectedDensity }}
          </button>
          <div v-if="densityMenuOpen" class="density-options" role="menu">
            <button
              v-for="option in densityOptions"
              :key="option.key"
              type="button"
              role="menuitemradio"
              :aria-checked="selectedDensity === option.key"
              :class="{ 'is-active': selectedDensity === option.key }"
              @click="selectDensity(option.key)"
            >
              <strong>{{ option.key }}</strong>
              <span>{{ option.label }}</span>
            </button>
          </div>
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
          <div class="guidance-page">
            <section class="guidance-hero">
              <p class="small-label">Reading Flow</p>
              <h2>{{ hasActiveReading ? 'Chapter Complete' : 'Ready to Read' }}</h2>
              <div v-if="currentMeta" class="chapter-context">
                <p>{{ currentMeta.book_title }}</p>
                <p>{{ chapterDetailText }}</p>
              </div>
              <p class="guidance-summary">{{ summaryText }}</p>
            </section>

            <div class="guide-action-panel">
              <p class="small-label">{{ guideActionTitle }}</p>
              <article v-for="card in cards" :key="card.id" class="guide-card">
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
