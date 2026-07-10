<!--
  Presents the click-to-lookup result and emits user intent only.
  Lookup requests, vocabulary mutations, positioning, and visibility state are
  owned by useWordLookup; this component deliberately performs no API calls.
-->
<script setup>
defineProps({
  error: { type: String, default: '' },
  isAnnotated: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  result: { type: Object, default: null },
  saving: { type: Boolean, default: false },
  sentence: { type: String, default: '' },
  style: { type: Object, default: () => ({}) },
  translation: { type: String, default: '' },
  visible: { type: Boolean, default: false },
  word: { type: String, default: '' },
})

defineEmits(['add', 'close', 'remove'])
</script>

<template>
  <aside v-if="visible" class="lookup-bubble" :style="style">
    <div class="lookup-head">
      <div>
        <p class="small-label">Lookup</p>
        <h3>{{ word }}</h3>
      </div>
      <button type="button" class="icon-button" aria-label="关闭查词" @click="$emit('close')">×</button>
    </div>

    <p v-if="loading" class="lookup-muted">正在查词...</p>
    <p v-else-if="error" class="lookup-error">{{ error }}</p>

    <template v-if="result">
      <p class="lookup-translation">{{ result.word_cn || translation || '暂无译文' }}</p>
      <p v-if="sentence" class="lookup-sentence">{{ sentence }}</p>
      <p v-if="result.sentence_cn" class="lookup-sentence-cn">{{ result.sentence_cn }}</p>
    </template>

    <div class="lookup-actions">
      <button
        v-if="!isAnnotated"
        type="button"
        :disabled="loading || saving || !(result?.word_cn || translation)"
        @click="$emit('add')"
      >添加标注</button>
      <button
        v-else
        type="button"
        :disabled="saving"
        @click="$emit('remove')"
      >取消标注</button>
    </div>
  </aside>
</template>
