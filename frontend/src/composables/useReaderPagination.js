/**
 * Owns the reader's CSS-column pagination state and DOM layout calculation.
 * It depends on rendered reading blocks supplied by the page coordinator and
 * deliberately does not fetch chapters, open bookmarks, or request agent cards.
 */
import { computed, nextTick, ref } from 'vue'

export function useReaderPagination({ hasActiveReading, renderedBlocks, onLayout } = {}) {
  const currentPage = ref(0)
  const readingViewport = ref(null)
  const readingFlow = ref(null)
  const pageStride = ref(0)
  const totalReadingPages = ref(0)

  const isGuidancePage = computed(() => (
    hasActiveReading.value
    && totalReadingPages.value > 0
    && currentPage.value >= totalReadingPages.value
  ))

  const flowTransform = computed(() => ({
    transform: `translateX(-${currentPage.value * pageStride.value}px)`,
  }))

  const canGoPrev = computed(() => currentPage.value > 0)
  const canGoNext = computed(() => (
    hasActiveReading.value
    && totalReadingPages.value > 0
    && currentPage.value < totalReadingPages.value
  ))

  function resetPagination() {
    currentPage.value = 0
    totalReadingPages.value = 0
    pageStride.value = 0
  }

  function nextPage() {
    if (canGoNext.value) currentPage.value += 1
  }

  function prevPage() {
    if (canGoPrev.value) currentPage.value -= 1
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
    await onLayout?.()
  }

  return {
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
  }
}
