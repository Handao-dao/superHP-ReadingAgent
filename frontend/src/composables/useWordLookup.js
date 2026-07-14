/**
 * Owns click-to-lookup state, contextual sentence extraction, and manual
 * annotation mutations. The page coordinator supplies the active unit/profile
 * and decides how vocabulary changes refresh the catalog and reader layout.
 * This composable does not navigate chapters or manage pagination itself.
 */
import { ref } from 'vue'
import { lookupWord } from '../api/lookup'
import { addVocabulary, fetchVocabulary, setMasteredByWord } from '../api/vocabulary'

export function useWordLookup({
  getProfileId,
  getReadingFlow,
  getUnitId,
  onVocabularyChanged,
} = {}) {
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
  let annotationLoadRevision = 0
  let lookupRequestRevision = 0

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
    // Invalidate an in-flight lookup so a late response cannot repopulate a
    // bubble that the user closed or that belongs to a previous reading unit.
    lookupRequestRevision += 1
    lookupVisible.value = false
    lookupLoading.value = false
    lookupSaving.value = false
    lookupError.value = ''
    lookupResult.value = null
  }

  function resetLookupAnnotations() {
    annotationLoadRevision += 1
    manualAnnotations.value = new Map()
    hiddenAnnotations.value = new Set()
  }

  async function loadLookupAnnotations(unitId) {
    const revision = ++annotationLoadRevision
    if (!unitId) {
      manualAnnotations.value = new Map()
      hiddenAnnotations.value = new Set()
      return
    }

    try {
      const result = await fetchVocabulary({ unitId })
      if (revision !== annotationLoadRevision) return

      const restoredManual = new Map()
      const restoredHidden = new Set()
      for (const item of result.items) {
        const key = normalizeWord(item.word)
        if (!key) continue
        if (item.mastered) {
          restoredHidden.add(key)
          continue
        }
        const translation = item.translation || item.global_translation
        if (translation) restoredManual.set(key, translation)
      }
      manualAnnotations.value = restoredManual
      hiddenAnnotations.value = restoredHidden
    } catch {
      if (revision !== annotationLoadRevision) return
      manualAnnotations.value = new Map()
      hiddenAnnotations.value = new Set()
    }
  }

  async function handleReadingClick(event) {
    const target = event.target.closest?.('[data-word]')
    if (!target || !getReadingFlow?.()?.contains(target)) {
      closeLookupBubble()
      return
    }

    const word = cleanWord(target.dataset.word || target.textContent || '')
    if (!word) return
    const revision = ++lookupRequestRevision

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
      const result = await lookupWord(word, lookupSentence.value, getProfileId?.())
      if (revision !== lookupRequestRevision) return
      if (!result.word_cn && lookupTranslation.value) result.word_cn = lookupTranslation.value
      lookupResult.value = result
    } catch (error) {
      if (revision !== lookupRequestRevision) return
      lookupError.value = error.message || '查词失败'
      if (lookupTranslation.value) {
        lookupResult.value = {
          word,
          word_cn: lookupTranslation.value,
          sentence_cn: '',
        }
      }
    } finally {
      if (revision === lookupRequestRevision) lookupLoading.value = false
    }
  }

  async function addLookupAnnotation() {
    const translation = lookupResult.value?.word_cn || lookupTranslation.value
    const unitId = getUnitId?.()
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
      await onVocabularyChanged?.()
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
      await setMasteredByWord(lookupWordText.value, true, getProfileId?.())
      const nextManual = new Map(manualAnnotations.value)
      const nextHidden = new Set(hiddenAnnotations.value)
      nextManual.delete(key)
      nextHidden.add(key)
      manualAnnotations.value = nextManual
      hiddenAnnotations.value = nextHidden
      lookupIsAnnotated.value = false
      closeLookupBubble()
      await onVocabularyChanged?.()
    } catch (error) {
      lookupError.value = error.message || '取消标注失败'
    } finally {
      lookupSaving.value = false
    }
  }

  return {
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
  }
}
