<!--
  Presents non-interactive reader states: annotation generation, session error,
  or an empty waiting screen. It receives already-resolved status text and does
  not start model work, recover sessions, or choose reading actions.
-->
<script setup>
defineProps({
  errorMessage: { type: String, default: '' },
  mode: { type: String, default: 'empty' },
  profileLabel: { type: String, default: '' },
  progressText: { type: String, default: '' },
  summary: { type: String, default: '' },
  unitCount: { type: Number, default: 0 },
})
</script>

<template>
  <div v-if="mode === 'generating'" class="summary-page">
    <p class="small-label">{{ progressText || 'Generating annotations...' }}</p>
    <h2>Chapter Summary</h2>
    <p>{{ summary }}</p>
  </div>

  <div v-else-if="mode === 'error'" class="summary-page error-state">
    <p class="small-label">Session Error</p>
    <h2>Unable to Continue</h2>
    <p>{{ errorMessage }}</p>
  </div>

  <div v-else class="summary-page empty-state">
    <p class="small-label">Waiting</p>
    <h2>Choose a Reading Action</h2>
    <p>{{ profileLabel }}当前有 {{ unitCount }} 个阅读单元。</p>
  </div>
</template>
