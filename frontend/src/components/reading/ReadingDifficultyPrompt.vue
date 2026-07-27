<!--
  Inserts one explicit consent step between the last reading page and the
  normal chapter-complete card. It only presents the evaluator's aggregate
  evidence; the parent owns navigation and recommendation-session handoff.
-->
<script setup>
import { computed } from 'vue'

const props = defineProps({
  alert: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  currentMeta: { type: Object, default: null },
  errorMessage: { type: String, default: '' },
})

defineEmits(['change-book', 'continue-reading'])

const evidence = computed(() => props.alert?.evidence || {})
const lookupDensity = computed(() => Number(evidence.value.lookup_density || 0).toFixed(1))
const observedChapters = computed(() => Number(evidence.value.observed_chapter_count || 0))
</script>

<template>
  <div class="guidance-page difficulty-prompt-page">
    <section class="guidance-hero">
      <p class="small-label">Reading Check-in</p>
      <h2>这本书读起来可能有些吃力</h2>
      <div v-if="currentMeta" class="chapter-context">
        <p>{{ currentMeta.book_title }}</p>
        <p>已完成 Chapter {{ currentMeta.chapter_no }}</p>
      </div>
      <p class="guidance-summary">
        最近 {{ observedChapters }} 章中，你平均每 300 词主动查词
        {{ lookupDensity }} 次。持续较高的查词频率可能会打断阅读节奏。
      </p>
    </section>

    <div class="guide-action-panel difficulty-prompt-actions">
      <p class="small-label">Choose your next step</p>
      <p>你想继续尝试这本书，还是让选书助手推荐一本更适合持续阅读的作品？</p>
      <p v-if="errorMessage" class="paper-alert" role="alert">
        {{ errorMessage }}
      </p>
      <div class="actions">
        <button
          type="button"
          :disabled="busy"
          @click="$emit('continue-reading')"
        >
          我仍想继续尝试
        </button>
        <button
          type="button"
          :disabled="busy"
          @click="$emit('change-book')"
        >
          好的，换一本
        </button>
      </div>
    </div>
  </div>
</template>
