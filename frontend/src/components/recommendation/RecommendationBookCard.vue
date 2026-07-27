<!--
  Presents verified local-catalog metadata for one recommended title.
  Selection and reading navigation remain owned by the page coordinator.
-->
<script setup>
defineProps({
  book: { type: Object, required: true },
})

function entryKindLabel(kind) {
  return {
    book: '单本',
    series: '系列',
    collection: '合集',
  }[kind] || '读物'
}

function lexileLabel(book) {
  if (book.lexile_min === book.lexile_max) return `${book.lexile_min}L`
  return `${book.lexile_min}L–${book.lexile_max}L`
}
</script>

<template>
  <article class="recommendation-book-card">
    <div class="recommendation-book-kicker">
      <span>{{ entryKindLabel(book.entry_kind) }}</span>
      <strong>{{ lexileLabel(book) }}</strong>
    </div>
    <h3>{{ book.title_en }}</h3>
    <p v-if="book.title_zh" class="recommendation-book-title-zh">{{ book.title_zh }}</p>
    <p v-if="book.author" class="recommendation-book-author">{{ book.author }}</p>
    <div v-if="book.genres?.length" class="recommendation-book-genres">
      <span v-for="genre in book.genres" :key="genre">{{ genre.replaceAll('_', ' ') }}</span>
    </div>
  </article>
</template>
