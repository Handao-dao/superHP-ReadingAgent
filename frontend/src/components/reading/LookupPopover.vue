<!--
  Presents the click-to-lookup result and emits user intent only.
  Lookup requests, vocabulary mutations, positioning, and visibility state are
  owned by useWordLookup; this component deliberately performs no API calls.
-->
<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
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

const bubble = ref(null)
const dragPosition = ref(null)
const dragging = ref(false)
let dragState = null

const positionedStyle = computed(() => {
  if (!dragPosition.value) return props.style
  return {
    ...props.style,
    left: `${dragPosition.value.left}px`,
    top: `${dragPosition.value.top}px`,
    right: 'auto',
    bottom: 'auto',
  }
})

function removeDragListeners() {
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', finishDrag)
  window.removeEventListener('pointercancel', finishDrag)
}

function startDrag(event) {
  if (event.button !== 0 || event.target.closest('button') || !bubble.value) return
  const rect = bubble.value.getBoundingClientRect()
  dragState = {
    pointerId: event.pointerId,
    offsetX: event.clientX - rect.left,
    offsetY: event.clientY - rect.top,
  }
  dragPosition.value = { left: rect.left, top: rect.top }
  dragging.value = true
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', finishDrag)
  window.addEventListener('pointercancel', finishDrag)
  event.preventDefault()
}

function handlePointerMove(event) {
  if (!dragState || event.pointerId !== dragState.pointerId || !bubble.value) return
  const edge = 8
  const rect = bubble.value.getBoundingClientRect()
  const maxLeft = Math.max(edge, window.innerWidth - rect.width - edge)
  const maxTop = Math.max(edge, window.innerHeight - rect.height - edge)
  dragPosition.value = {
    left: Math.min(maxLeft, Math.max(edge, event.clientX - dragState.offsetX)),
    top: Math.min(maxTop, Math.max(edge, event.clientY - dragState.offsetY)),
  }
}

function finishDrag(event) {
  if (dragState && event?.pointerId !== undefined && event.pointerId !== dragState.pointerId) return
  dragState = null
  dragging.value = false
  removeDragListeners()
}

watch(() => props.style, () => {
  finishDrag()
  dragPosition.value = null
})

watch(() => props.visible, (visible) => {
  if (visible) return
  finishDrag()
  dragPosition.value = null
})

onBeforeUnmount(removeDragListeners)
</script>

<template>
  <aside
    v-if="visible"
    ref="bubble"
    class="lookup-bubble"
    :class="{ 'is-dragged': dragPosition, 'is-dragging': dragging }"
    :style="positionedStyle"
  >
    <div class="lookup-head" title="拖动卡片" @pointerdown="startDrag">
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
