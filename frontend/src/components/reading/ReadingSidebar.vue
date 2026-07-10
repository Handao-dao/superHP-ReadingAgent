<!--
  Presents profile choices, grouped chapters, status badges, and saved
  bookmarks. It owns display formatting only and emits user intent; catalog
  loading, bookmark persistence, and chapter navigation remain outside.
-->
<script setup>
const props = defineProps({
  bookmarkError: { type: String, default: '' },
  bookmarksByUnit: { type: Object, default: () => new Map() },
  bookmarksLoading: { type: Boolean, default: false },
  books: { type: Array, default: () => [] },
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

function chapterNumberLabel(chapter) {
  if (chapter.profile_id === 'classical_chinese') return String(chapter.chapter_no)
  return String(chapter.chapter_no).padStart(2, '0')
}

function chapterNumberKicker(chapter) {
  return chapter.profile_id === 'classical_chinese' ? '篇' : 'CH'
}

function bookUnitCount(book) {
  const unit = props.selectedProfileId === 'classical_chinese' ? '篇' : 'chapters'
  return `${book.chapters.length} ${unit}`
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
  const normalized = String(value).replace(' ', 'T')
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
</script>

<template>
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
          @click="$emit('select-profile', profile.id)"
        >{{ profile.id === 'classical_chinese' ? '文言文' : '英文小说' }}</button>
      </div>
    </div>

    <div v-if="profileError" class="sidebar-error">{{ profileError }}</div>
    <div v-if="listError" class="sidebar-error">{{ listError }}</div>
    <div v-else-if="listLoading" class="sidebar-loading">正在读取目录...</div>
    <div v-if="bookmarksLoading" class="sidebar-loading">正在读取书签...</div>
    <div v-if="bookmarkError" class="sidebar-error">{{ bookmarkError }}</div>

    <nav v-if="!listError && !listLoading" class="book-list">
      <section v-for="book in books" :key="book.id" class="book-group">
        <div class="book-heading">
          <h3>{{ book.title }}</h3>
          <span>{{ bookUnitCount(book) }}</span>
        </div>
        <div v-for="chapter in book.chapters" :key="chapter.id" class="chapter-entry">
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
                @click="$emit('open-bookmark', bookmark)"
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
                @click="$emit('delete-bookmark', bookmark)"
              >×</button>
            </div>
          </div>
        </div>
      </section>
    </nav>
  </aside>

  <button type="button" class="sidebar-scrim" aria-label="关闭目录" @click="$emit('close')"></button>
</template>
