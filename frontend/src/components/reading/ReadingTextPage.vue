<!--
  Renders the paginated reading blocks and owns the viewport/flow DOM nodes.
  It reports those elements to the parent for CSS-column measurement and emits
  raw reading clicks for useWordLookup; it does not calculate pages or fetch text.
-->
<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps({
  annotated: { type: Boolean, default: false },
  blocks: { type: Array, default: () => [] },
  flowTransform: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['elements-change', 'reading-click'])
const readingViewport = ref(null)
const readingFlow = ref(null)

onMounted(() => {
  emit('elements-change', {
    flow: readingFlow.value,
    viewport: readingViewport.value,
  })
})

onBeforeUnmount(() => {
  emit('elements-change', { flow: null, viewport: null })
})
</script>

<template>
  <div class="reading-page" :class="{ 'is-annotated': annotated }">
    <div ref="readingViewport" class="reading-viewport">
      <div
        ref="readingFlow"
        class="reading-flow"
        :style="flowTransform"
        @click="$emit('reading-click', $event)"
      >
        <div
          v-for="(html, index) in blocks"
          :key="index"
          class="reading-block"
          v-html="html"
        ></div>
      </div>
    </div>
  </div>
</template>
