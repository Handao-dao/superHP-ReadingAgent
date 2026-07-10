/**
 * Owns bookmark persistence, list state, grouping, and saved-page resolution.
 * The page coordinator supplies the current reader snapshot and remains
 * responsible for WebSocket navigation and applying a resolved page index.
 * This composable does not open chapters or change the active reader view.
 */
import { computed, ref } from 'vue'
import { addBookmark, deleteBookmark, fetchBookmarks } from '../api/bookmarks'

export function useBookmarks({
  getActiveChapter,
  getCurrentPage,
  getParagraphs,
  getReaderMode,
  getTotalPages,
  stripAnnotationMarkers,
} = {}) {
  const bookmarks = ref([])
  const bookmarksLoading = ref(false)
  const bookmarkError = ref('')
  const bookmarkSaving = ref(false)
  const deletingBookmarkId = ref(null)
  const pendingBookmarkJump = ref(null)

  const bookmarksByUnit = computed(() => {
    const groups = new Map()
    for (const bookmark of bookmarks.value) {
      if (!groups.has(bookmark.unit_id)) groups.set(bookmark.unit_id, [])
      groups.get(bookmark.unit_id).push(bookmark)
    }
    return groups
  })

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

  function cleanBookmarkExcerpt(text = '') {
    return stripAnnotationMarkers(text)
      .replace(/^#{1,6}\s+/, '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 120)
  }

  function currentBookmarkExcerpt() {
    const paragraphs = getParagraphs?.() || []
    const currentPage = getCurrentPage?.() || 0
    const activeChapter = getActiveChapter?.()
    const block = paragraphs[Math.min(currentPage, Math.max(0, paragraphs.length - 1))]
    return cleanBookmarkExcerpt(block || activeChapter?.body || '')
  }

  async function saveCurrentBookmark() {
    const activeChapter = getActiveChapter?.()
    const meta = activeChapter?.meta
    const bodyKind = activeChapter?.body_kind
    if (!meta || !bodyKind || getReaderMode?.() !== 'reading') return
    bookmarkSaving.value = true
    bookmarkError.value = ''
    try {
      const totalPages = Math.max(0, getTotalPages?.() || 0)
      const pageIndex = Math.max(0, getCurrentPage?.() || 0)
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

  async function deleteBookmarkEntry(bookmark) {
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

  function queueBookmarkJump(bookmark) {
    pendingBookmarkJump.value = bookmark
  }

  function resolvePendingBookmarkJump({ activeUnitId, bodyKind, totalPages }) {
    const bookmark = pendingBookmarkJump.value
    if (!bookmark || totalPages <= 0) return null
    if (bookmark.unit_id !== activeUnitId || bookmark.body_kind !== bodyKind) return null

    const savedPage = Number(bookmark.page_index)
    const ratio = Number(bookmark.progress_ratio)
    const ratioPage = Number.isFinite(ratio)
      ? Math.round((totalPages - 1) * Math.min(1, Math.max(0, ratio)))
      : 0
    const targetPage = Number.isInteger(savedPage) && savedPage >= 0 && savedPage < totalPages
      ? savedPage
      : ratioPage
    pendingBookmarkJump.value = null
    return Math.min(totalPages - 1, Math.max(0, targetPage))
  }

  return {
    bookmarkError,
    bookmarksByUnit,
    bookmarksLoading,
    bookmarkSaving,
    deleteBookmarkEntry,
    deletingBookmarkId,
    loadBookmarks,
    queueBookmarkJump,
    resolvePendingBookmarkJump,
    saveCurrentBookmark,
  }
}
