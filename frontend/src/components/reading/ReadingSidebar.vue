<!-- Drill-down library navigation: collection → book → chapter. -->
<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  bookmarkError: { type: String, default: '' },
  bookmarksByUnit: { type: Object, default: () => new Map() },
  bookmarksLoading: { type: Boolean, default: false },
  catalogError: { type: String, default: '' },
  collections: { type: Array, default: () => [] },
  currentChapterId: { type: String, default: '' },
  deletingBookmarkId: { type: [Number, String], default: null },
  isGenerating: { type: Boolean, default: false },
  listError: { type: String, default: '' },
  listLoading: { type: Boolean, default: false },
  profileError: { type: String, default: '' },
  profileOptions: { type: Array, default: () => [] },
  selectedProfileId: { type: String, default: '' },
})

defineEmits(['close', 'delete-bookmark', 'open-bookmark', 'select-chapter', 'select-profile'])

const selectedCollectionId = ref('')
const selectedBookId = ref('')
const searchQuery = ref('')

const selectedCollection = computed(() => {
  return props.collections.find((collection) => collection.id === selectedCollectionId.value) || null
})

const selectedBook = computed(() => {
  return selectedCollection.value?.books.find((book) => book.id === selectedBookId.value) || null
})

const navigationLevel = computed(() => {
  if (selectedBook.value) return 'chapters'
  if (selectedCollection.value) return 'books'
  return 'collections'
})

const searchPlaceholder = computed(() => {
  if (navigationLevel.value === 'chapters') return 'Search chapters'
  if (navigationLevel.value === 'books') return 'Search books'
  return 'Search collections'
})

const normalizedQuery = computed(() => searchQuery.value.trim().toLocaleLowerCase())

const visibleCollections = computed(() => {
  if (!normalizedQuery.value) return props.collections
  return props.collections.filter((collection) => {
    return `${collection.title} ${collection.author}`.toLocaleLowerCase().includes(normalizedQuery.value)
  })
})

const visibleBooks = computed(() => {
  const books = selectedCollection.value?.books || []
  if (!normalizedQuery.value) return books
  return books.filter((book) => book.title.toLocaleLowerCase().includes(normalizedQuery.value))
})

const visibleChapters = computed(() => {
  const chapters = selectedBook.value?.chapters || []
  if (!normalizedQuery.value) return chapters
  return chapters.filter((chapter) => chapter.chapter_title.toLocaleLowerCase().includes(normalizedQuery.value))
})

function openCollection(collection) {
  selectedCollectionId.value = collection.id
  selectedBookId.value = ''
  searchQuery.value = ''
}

function openBook(book) {
  selectedBookId.value = book.id
  searchQuery.value = ''
}

function showCollections() {
  selectedCollectionId.value = ''
  selectedBookId.value = ''
  searchQuery.value = ''
}

function showBooks() {
  selectedBookId.value = ''
  searchQuery.value = ''
}

function goBack() {
  if (selectedBook.value) showBooks()
  else showCollections()
}

function collectionUnitCount(collection) {
  return collection.books.reduce((count, book) => count + book.chapters.length, 0)
}

function bookReadCount(book) {
  return book.chapters.filter((chapter) => chapter.status === 'read').length
}

function chapterNumberLabel(chapter) {
  return chapter.profile_id === 'classical_chinese'
    ? String(chapter.chapter_no)
    : String(chapter.chapter_no).padStart(2, '0')
}

function chapterNumberKicker(chapter) {
  return chapter.profile_id === 'classical_chinese' ? '篇' : 'CH'
}

function chapterBadgeText(chapter, type) {
  const bookmarkCount = props.bookmarksByUnit.get(chapter.id)?.length || 0
  if (chapter.profile_id === 'classical_chinese') {
    if (type === 'read') return '已读'
    if (type === 'annotated') return '注释'
    if (type === 'vocab') return `${chapter.vocab_count} 重点`
    if (type === 'bookmark') return `${bookmarkCount} 书签`
  }
  if (type === 'read') return 'Read'
  if (type === 'annotated') return 'Annotated'
  if (type === 'vocab') return `${chapter.vocab_count} words`
  if (type === 'bookmark') return `${bookmarkCount} marks`
  return ''
}

function formatBookmarkTime(value = '') {
  if (!value) return ''
  const date = new Date(String(value).replace(' ', 'T'))
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

watch(() => props.selectedProfileId, showCollections)

watch(() => props.collections, () => {
  if (selectedCollectionId.value && !selectedCollection.value) showCollections()
  else if (selectedBookId.value && !selectedBook.value) showBooks()
}, { deep: true })
</script>

<template>
  <aside class="chapter-sidebar" aria-label="章节目录">
    <header class="sidebar-header">
      <div class="sidebar-title-row">
        <div>
          <p class="eyebrow">Library</p>
          <h2>目录</h2>
        </div>
        <button type="button" class="sidebar-close" aria-label="关闭目录" @click="$emit('close')">×</button>
      </div>

      <div class="profile-switch" aria-label="阅读场景">
        <button
          v-for="profile in profileOptions"
          :key="profile.id"
          type="button"
          :class="{ 'is-active': selectedProfileId === profile.id }"
          :disabled="isGenerating"
          @click="$emit('select-profile', profile.id)"
        >{{ profile.id === 'classical_chinese' ? '文言文' : '英文小说' }}</button>
      </div>

      <nav v-if="navigationLevel !== 'collections'" class="library-breadcrumb" aria-label="目录路径">
        <button type="button" @click="showCollections">Library</button>
        <span aria-hidden="true">/</span>
        <button
          v-if="selectedCollection"
          type="button"
          :aria-current="navigationLevel === 'books' ? 'page' : undefined"
          @click="showBooks"
        >{{ selectedCollection.title }}</button>
        <template v-if="selectedBook">
          <span aria-hidden="true">/</span>
          <span aria-current="page">{{ selectedBook.title }}</span>
        </template>
      </nav>

      <label class="library-search">
        <span class="sr-only">{{ searchPlaceholder }}</span>
        <input v-model="searchQuery" type="search" :placeholder="searchPlaceholder" autocomplete="off">
      </label>
    </header>

    <div v-if="profileError" class="sidebar-error">{{ profileError }}</div>
    <div v-if="listError" class="sidebar-error">{{ listError }}</div>
    <div v-else-if="listLoading" class="sidebar-loading">正在读取目录...</div>
    <div v-if="catalogError && !listError" class="sidebar-warning">{{ catalogError }}，已按图书自动整理。</div>
    <div v-if="bookmarksLoading" class="sidebar-loading">正在读取书签...</div>
    <div v-if="bookmarkError" class="sidebar-error">{{ bookmarkError }}</div>

    <nav v-if="!listError && !listLoading" class="directory-stage" :data-level="navigationLevel">
      <div v-if="navigationLevel !== 'collections'" class="directory-heading">
        <button type="button" class="directory-back" @click="goBack">
          <span aria-hidden="true">‹</span> Back
        </button>
        <p>{{ navigationLevel === 'chapters' ? 'Chapters' : 'Books' }}</p>
      </div>

      <template v-if="navigationLevel === 'collections'">
        <p class="directory-kicker">Collections</p>
        <p v-if="visibleCollections.length === 0" class="library-empty">No matches</p>
        <button
          v-for="collection in visibleCollections"
          :key="collection.id"
          type="button"
          class="directory-row collection-row"
          @click="openCollection(collection)"
        >
          <span class="directory-copy">
            <strong>{{ collection.title }}</strong>
            <small v-if="collection.author">{{ collection.author }}</small>
          </span>
          <span class="directory-meta">{{ collection.books.length }} books · {{ collectionUnitCount(collection) }}</span>
          <span class="directory-arrow" aria-hidden="true">›</span>
        </button>
      </template>

      <template v-else-if="navigationLevel === 'books'">
        <div class="directory-context">
          <strong>{{ selectedCollection.title }}</strong>
          <small v-if="selectedCollection.author">{{ selectedCollection.author }}</small>
        </div>
        <p v-if="visibleBooks.length === 0" class="library-empty">No matches</p>
        <button
          v-for="book in visibleBooks"
          :key="book.id"
          type="button"
          class="directory-row book-row"
          :class="{ 'is-current': book.chapters.some((chapter) => chapter.id === currentChapterId) }"
          @click="openBook(book)"
        >
          <span class="directory-copy">
            <strong>{{ book.title }}</strong>
            <small>{{ bookReadCount(book) }}/{{ book.chapters.length }} read</small>
          </span>
          <span class="directory-arrow" aria-hidden="true">›</span>
        </button>
      </template>

      <template v-else>
        <div class="directory-context">
          <strong>{{ selectedBook.title }}</strong>
          <small>{{ selectedBook.chapters.length }} chapters</small>
        </div>
        <p v-if="visibleChapters.length === 0" class="library-empty">No matches</p>
        <div v-for="chapter in visibleChapters" :key="chapter.id" class="chapter-entry directory-chapter">
          <button
            type="button"
            class="chapter-item"
            :class="{ 'is-active': chapter.id === currentChapterId, 'is-read': chapter.status === 'read' }"
            :disabled="isGenerating"
            @click="$emit('select-chapter', chapter)"
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

          <div v-if="chapter.id === currentChapterId && bookmarksByUnit.get(chapter.id)?.length" class="bookmark-list">
            <div v-for="bookmark in bookmarksByUnit.get(chapter.id)" :key="bookmark.id" class="bookmark-item">
              <button type="button" class="bookmark-open" :disabled="isGenerating" @click="$emit('open-bookmark', bookmark)">
                <span>{{ bookmark.label || `Page ${bookmark.page_index + 1}` }}</span>
                <small>{{ bookmark.body_kind === 'annotated' ? 'Annotated' : 'Original' }} · {{ formatBookmarkTime(bookmark.created_at) }}</small>
                <em v-if="bookmark.excerpt">{{ bookmark.excerpt }}</em>
              </button>
              <button
                type="button"
                class="bookmark-delete"
                :disabled="deletingBookmarkId === bookmark.id"
                aria-label="删除书签"
                @click="$emit('delete-bookmark', bookmark)"
              >×</button>
            </div>
          </div>
        </div>
      </template>
    </nav>
  </aside>

  <button type="button" class="sidebar-scrim" aria-label="关闭目录" @click="$emit('close')"></button>
</template>
