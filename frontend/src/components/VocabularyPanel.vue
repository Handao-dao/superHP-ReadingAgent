<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { deleteVocabulary, fetchVocabulary, setMastered } from '../api/vocabulary'

const props = defineProps({
  collections: {
    type: Array,
    default: () => [],
  },
  currentUnitId: {
    type: String,
    default: '',
  },
  currentTitle: {
    type: String,
    default: '',
  },
  selectedUnitId: {
    type: String,
    default: '',
  },
  profileId: {
    type: String,
    default: 'english_novel',
  },
  refreshKey: {
    type: Number,
    default: 0,
  },
})

const emit = defineEmits(['changed', 'update:selectedUnitId'])

const items = ref([])
const loading = ref(false)
const errorMessage = ref('')
const tab = ref('active')
const search = ref('')
const selectedCollectionId = ref('')
const selectedBookId = ref('')
let vocabularyLoadRevision = 0

const posLabels = {
  noun: '名词',
  verb: '动词',
  adjective: '形容词',
  adverb: '副词',
  phrase: '短语',
  other: '其他',
  重点实词: '重点实词',
  重点虚词: '重点虚词',
  通假字: '通假字',
  古今异义: '古今异义',
  词类活用: '词类活用',
  虚词用法: '虚词用法',
  特殊句式: '特殊句式',
  其他: '其他',
}

const profileCopy = computed(() => {
  if (props.profileId === 'classical_chinese') {
    return {
      eyebrow: 'Knowledge Points',
      title: '文言重点',
      allUnits: '全部篇目',
      allCollections: '全部选集',
      allBooks: '全部篇目',
      collectionLabel: '选集',
      bookLabel: '篇目',
      chapterLabel: '章节',
      currentUnit: '当前篇目',
      searchPlaceholder: '字词 / 释义 / 原文语境',
      loading: '正在读取文言重点...',
      empty: '这里暂时没有文言重点。',
    }
  }
  return {
    eyebrow: 'Vocabulary',
    title: '生词表',
    allUnits: '所有章节',
    allCollections: 'All collections',
    allBooks: 'All books',
    collectionLabel: '系列',
    bookLabel: '图书',
    chapterLabel: '章节',
    currentUnit: '当前章节',
    searchPlaceholder: 'word / 译文 / context',
    loading: '正在读取生词...',
    empty: '这里暂时没有生词。',
  }
})

const selectedCollection = computed(() => {
  return props.collections.find((collection) => collection.id === selectedCollectionId.value) || null
})

const availableBooks = computed(() => selectedCollection.value?.books || [])

const selectedBook = computed(() => {
  return availableBooks.value.find((book) => book.id === selectedBookId.value) || null
})

const availableChapters = computed(() => selectedBook.value?.chapters || [])

const selectedChapter = computed(() => {
  return availableChapters.value.find((chapter) => chapter.id === props.selectedUnitId) || null
})

const selectedScopeTitle = computed(() => {
  if (selectedChapter.value) return `${selectedChapter.value.chapter_no}. ${selectedChapter.value.chapter_title}`
  if (selectedBook.value) return selectedBook.value.title
  if (selectedCollection.value) return selectedCollection.value.title
  return profileCopy.value.allUnits
})

const scopedItems = computed(() => {
  if (props.selectedUnitId) return items.value.filter((item) => item.unit_id === props.selectedUnitId)
  if (selectedBook.value) return items.value.filter((item) => item.book_id === selectedBook.value.id)
  if (selectedCollection.value) {
    const bookIds = new Set(selectedCollection.value.books.map((book) => book.id))
    return items.value.filter((item) => bookIds.has(item.book_id))
  }
  return items.value
})

const filteredItems = computed(() => {
  const query = search.value.trim().toLowerCase()
  return scopedItems.value.filter((item) => {
    if (tab.value === 'active' && item.mastered) return false
    if (tab.value === 'mastered' && !item.mastered) return false
    if (!query) return true
    return (
      item.word.toLowerCase().includes(query) ||
      item.translation.includes(search.value.trim()) ||
      item.context.toLowerCase().includes(query)
    )
  })
})

const activeCount = computed(() => scopedItems.value.filter((item) => !item.mastered).length)
const masteredCount = computed(() => scopedItems.value.filter((item) => item.mastered).length)

function updateSelectedCollection(event) {
  selectedCollectionId.value = event.target.value
  selectedBookId.value = ''
  emit('update:selectedUnitId', '')
}

function updateSelectedBook(event) {
  selectedBookId.value = event.target.value
  emit('update:selectedUnitId', '')
}

function updateSelectedUnitId(event) {
  emit('update:selectedUnitId', event.target.value)
}

function syncHierarchyFromUnit(unitId) {
  if (!unitId) return
  for (const collection of props.collections) {
    for (const book of collection.books) {
      if (book.chapters.some((chapter) => chapter.id === unitId)) {
        selectedCollectionId.value = collection.id
        selectedBookId.value = book.id
        return
      }
    }
  }
}

async function loadVocabulary() {
  const revision = ++vocabularyLoadRevision
  const profileId = props.profileId
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await fetchVocabulary({ profileId })
    if (revision !== vocabularyLoadRevision) return
    items.value = result.items
  } catch (error) {
    if (revision !== vocabularyLoadRevision) return
    errorMessage.value = error.message || '生词表加载失败'
  } finally {
    if (revision === vocabularyLoadRevision) loading.value = false
  }
}

async function toggleMastered(item) {
  try {
    await setMastered(item.id, !item.mastered)
    item.mastered = !item.mastered
    emit('changed')
  } catch (error) {
    errorMessage.value = error.message || '更新掌握状态失败'
  }
}

async function removeItem(item) {
  try {
    await deleteVocabulary(item.id)
    items.value = items.value.filter((candidate) => candidate.id !== item.id)
    emit('changed')
  } catch (error) {
    errorMessage.value = error.message || '删除生词失败'
  }
}

watch(() => props.refreshKey, loadVocabulary)
watch(() => props.profileId, () => {
  selectedCollectionId.value = ''
  selectedBookId.value = ''
  emit('update:selectedUnitId', '')
  loadVocabulary()
})
watch(() => props.selectedUnitId, syncHierarchyFromUnit, { immediate: true })
watch(() => props.collections, () => syncHierarchyFromUnit(props.selectedUnitId), { deep: true })

onMounted(loadVocabulary)
</script>

<template>
  <section class="vocabulary-panel">
    <header class="vocabulary-header">
      <div>
        <p class="small-label">{{ profileCopy.eyebrow }}</p>
        <h2>{{ profileCopy.title }}</h2>
        <p>{{ selectedScopeTitle }}</p>
      </div>
      <div class="vocab-stats">
        <span>{{ activeCount }} 未掌握</span>
        <span>{{ masteredCount }} 已掌握</span>
      </div>
    </header>

    <div class="vocab-toolbar">
      <div class="segmented-control" aria-label="生词状态">
        <button type="button" :class="{ 'is-active': tab === 'active' }" @click="tab = 'active'">未掌握</button>
        <button type="button" :class="{ 'is-active': tab === 'mastered' }" @click="tab = 'mastered'">已掌握</button>
      </div>
      <label class="vocab-search">
        <span>搜索</span>
        <input v-model="search" type="search" :placeholder="profileCopy.searchPlaceholder" />
      </label>
      <div class="vocab-scope-filters" aria-label="生词范围">
        <label class="chapter-select">
          <span>{{ profileCopy.collectionLabel }}</span>
          <select
            :value="selectedCollectionId"
            :aria-label="profileCopy.collectionLabel"
            @change="updateSelectedCollection"
          >
            <option value="">{{ profileCopy.allCollections }}</option>
            <option v-for="collection in collections" :key="collection.id" :value="collection.id">
              {{ collection.title }}
            </option>
          </select>
        </label>
        <label class="chapter-select">
          <span>{{ profileCopy.bookLabel }}</span>
          <select
            :value="selectedBookId"
            :disabled="!selectedCollection"
            :aria-label="profileCopy.bookLabel"
            @change="updateSelectedBook"
          >
            <option value="">{{ profileCopy.allBooks }}</option>
            <option v-for="book in availableBooks" :key="book.id" :value="book.id">
              {{ book.title }}
            </option>
          </select>
        </label>
        <label class="chapter-select">
          <span>{{ profileCopy.chapterLabel }}</span>
          <select
            :value="selectedUnitId"
            :disabled="!selectedBook"
            :aria-label="profileCopy.chapterLabel"
            @change="updateSelectedUnitId"
          >
            <option value="">{{ profileCopy.allUnits }}</option>
          <option
            v-for="chapter in availableChapters"
            :key="chapter.id"
            :value="chapter.id"
          >
            {{ chapter.chapter_no }}. {{ chapter.chapter_title }}
          </option>
          </select>
        </label>
      </div>
    </div>

    <p v-if="errorMessage" class="vocab-alert" role="status">{{ errorMessage }}</p>
    <p v-else-if="loading" class="vocab-empty">{{ profileCopy.loading }}</p>
    <p v-else-if="filteredItems.length === 0" class="vocab-empty">{{ profileCopy.empty }}</p>

    <div v-else class="vocab-table">
      <article v-for="item in filteredItems" :key="item.id" class="vocab-row">
        <div class="vocab-word-main">
          <h3>
            <span>{{ item.word }}</span>
            <span class="pos-badge">{{ posLabels[item.pos] || posLabels.other }}</span>
          </h3>
          <p>{{ item.translation || item.global_translation }}</p>
        </div>
        <p class="vocab-context">{{ item.context || '暂无例句' }}</p>
        <div class="vocab-row-actions">
          <button type="button" @click="toggleMastered(item)">
            {{ item.mastered ? '重新学习' : '已掌握' }}
          </button>
          <button type="button" class="ghost-danger" @click="removeItem(item)">删除</button>
        </div>
      </article>
    </div>
  </section>
</template>
