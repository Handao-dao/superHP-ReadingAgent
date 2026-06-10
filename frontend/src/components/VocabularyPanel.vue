<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { deleteVocabulary, fetchVocabulary, setMastered } from '../api/vocabulary'

const props = defineProps({
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
  chapters: {
    type: Array,
    default: () => [],
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

const posLabels = {
  noun: '名词',
  verb: '动词',
  adjective: '形容词',
  adverb: '副词',
  phrase: '短语',
  other: '其他',
}

const selectedChapterTitle = computed(() => {
  if (!props.selectedUnitId) return '所有章节'
  const chapter = props.chapters.find((item) => item.id === props.selectedUnitId)
  if (!chapter) return props.currentTitle || '当前章节'
  return `${chapter.chapter_no}. ${chapter.chapter_title}`
})

const scopedItems = computed(() => {
  if (!props.selectedUnitId) return items.value
  return items.value.filter((item) => item.unit_id === props.selectedUnitId)
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

function updateSelectedUnitId(event) {
  emit('update:selectedUnitId', event.target.value)
}

async function loadVocabulary() {
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await fetchVocabulary()
    items.value = result.items
  } catch (error) {
    errorMessage.value = error.message || '生词表加载失败'
  } finally {
    loading.value = false
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

onMounted(loadVocabulary)
</script>

<template>
  <section class="vocabulary-panel">
    <header class="vocabulary-header">
      <div>
        <p class="small-label">Vocabulary</p>
        <h2>生词表</h2>
        <p>{{ selectedChapterTitle }}</p>
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
        <input v-model="search" type="search" placeholder="word / 译文 / context" />
      </label>
      <label class="chapter-select">
        <span>章节</span>
        <select :value="selectedUnitId" @change="updateSelectedUnitId">
          <option value="">全部章节</option>
          <option
            v-for="chapter in chapters"
            :key="chapter.id"
            :value="chapter.id"
          >
            {{ chapter.chapter_no }}. {{ chapter.chapter_title }}
          </option>
        </select>
      </label>
    </div>

    <p v-if="errorMessage" class="vocab-alert" role="status">{{ errorMessage }}</p>
    <p v-else-if="loading" class="vocab-empty">正在读取生词...</p>
    <p v-else-if="filteredItems.length === 0" class="vocab-empty">这里暂时没有生词。</p>

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
