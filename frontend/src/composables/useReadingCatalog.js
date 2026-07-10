/**
 * Owns the available reading profiles, chapter catalog, loading errors, book
 * grouping, and persisted profile selection. The page coordinator decides how
 * a profile change resets the active WebSocket session and reader UI.
 * This composable does not open chapters or send reading actions.
 */
import { computed, ref, watch } from 'vue'
import { listChapters } from '../api/chapters'
import { listProfiles } from '../api/profiles'

const PROFILE_STORAGE_KEY = 'superhp_profile_id'

export function useReadingCatalog() {
  const chapters = ref([])
  const profiles = ref([])
  const listLoading = ref(false)
  const listErrorMessage = ref('')
  const profileErrorMessage = ref('')
  const selectedProfileId = ref(localStorage.getItem(PROFILE_STORAGE_KEY) || 'english_novel')

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

  async function loadChapterCatalog() {
    listLoading.value = true
    listErrorMessage.value = ''
    try {
      const loaded = await listChapters(selectedProfileId.value)
      chapters.value = loaded
      return loaded
    } catch (error) {
      listErrorMessage.value = error.message || '阅读单元列表加载失败'
      return null
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

  watch(selectedProfileId, (profileId) => {
    localStorage.setItem(PROFILE_STORAGE_KEY, profileId)
  })

  return {
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
  }
}
