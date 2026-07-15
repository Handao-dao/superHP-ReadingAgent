/**
 * Owns the available reading profiles, chapter catalog, loading errors, book
 * grouping, and persisted profile selection. The page coordinator decides how
 * a profile change resets the active WebSocket session and reader UI.
 * This composable does not open chapters or send reading actions.
 */
import { computed, ref, watch } from 'vue'
import { listLibraryCollections } from '../api/library'
import { listProfiles } from '../api/profiles'
import { listUnits } from '../api/units'

const PROFILE_STORAGE_KEY = 'superhp_profile_id'

export function useReadingCatalog() {
  const chapters = ref([])
  const catalogCollections = ref([])
  const profiles = ref([])
  const catalogErrorMessage = ref('')
  const listLoading = ref(false)
  const listErrorMessage = ref('')
  const profileErrorMessage = ref('')
  const selectedProfileId = ref(localStorage.getItem(PROFILE_STORAGE_KEY) || 'english_novel')
  let chapterLoadRevision = 0

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

  const libraryCollections = computed(() => {
    const booksById = new Map(chaptersByBook.value.map((book) => [book.id, book]))
    const configured = catalogCollections.value
      .filter((collection) => collection.profile_id === selectedProfileId.value)
      .slice()
      .sort((a, b) => a.order - b.order)
      .map((collection) => ({
        ...collection,
        books: collection.books
          .slice()
          .sort((a, b) => a.order - b.order)
          .map((book) => booksById.get(book.id))
          .filter(Boolean),
      }))
      .filter((collection) => collection.books.length > 0)

    const configuredBookIds = new Set(configured.flatMap((collection) => collection.books.map((book) => book.id)))
    const unconfiguredBooks = chaptersByBook.value.filter((book) => !configuredBookIds.has(book.id))
    if (unconfiguredBooks.length === 0) return configured

    return [
      ...configured,
      {
        id: `${selectedProfileId.value}-other`,
        profile_id: selectedProfileId.value,
        title: selectedProfileId.value === 'classical_chinese' ? '其他选篇' : 'Other Books',
        author: '',
        order: Number.MAX_SAFE_INTEGER,
        books: unconfiguredBooks,
      },
    ]
  })

  async function loadChapterCatalog() {
    const revision = ++chapterLoadRevision
    const profileId = selectedProfileId.value
    listLoading.value = true
    listErrorMessage.value = ''
    try {
      const loaded = await listUnits(profileId)
      if (revision !== chapterLoadRevision) return null
      chapters.value = loaded
      return loaded
    } catch (error) {
      if (revision !== chapterLoadRevision) return null
      listErrorMessage.value = error.message || '阅读单元列表加载失败'
      return null
    } finally {
      if (revision === chapterLoadRevision) listLoading.value = false
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

  async function loadLibraryCatalog() {
    catalogErrorMessage.value = ''
    try {
      catalogCollections.value = await listLibraryCollections()
    } catch (error) {
      catalogCollections.value = []
      catalogErrorMessage.value = error.message || '书库结构加载失败'
    }
  }

  watch(selectedProfileId, (profileId) => {
    localStorage.setItem(PROFILE_STORAGE_KEY, profileId)
  })

  return {
    catalogErrorMessage,
    chapters,
    chaptersByBook,
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
  }
}
