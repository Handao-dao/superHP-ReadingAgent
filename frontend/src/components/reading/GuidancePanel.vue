<!--
  Presents guided-reading context and the available agent card actions.
  The parent owns action routing, WebSocket state, and chapter
  navigation; this component only emits the action selected by the reader.
-->
<script setup>
defineProps({
  busy: { type: Boolean, default: false },
  canSend: { type: Boolean, default: false },
  cards: { type: Array, default: () => [] },
  chapterDetail: { type: String, default: '' },
  currentMeta: { type: Object, default: null },
  hasActiveReading: { type: Boolean, default: false },
  summary: { type: String, default: '' },
  title: { type: String, default: '' },
})

defineEmits(['action'])
</script>

<template>
  <div class="guidance-page">
    <section class="guidance-hero">
      <p class="small-label">Reading Flow</p>
      <h2>{{ hasActiveReading ? 'Chapter Complete' : 'Ready to Read' }}</h2>
      <div v-if="currentMeta" class="chapter-context">
        <p>{{ currentMeta.book_title }}</p>
        <p>{{ chapterDetail }}</p>
      </div>
      <p class="guidance-summary">{{ summary }}</p>
    </section>

    <div class="guide-action-panel">
      <p class="small-label">{{ title }}</p>
      <article v-for="card in cards" :key="card.id" class="guide-card">
        <div class="actions">
          <button
            v-for="action in card.actions"
            :key="`${card.id}-${action.id}`"
            type="button"
            :disabled="!canSend || busy"
            @click="$emit('action', action)"
          >{{ action.label }}</button>
        </div>
      </article>
    </div>
  </div>
</template>
