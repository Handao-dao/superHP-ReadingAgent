<!--
  Presents the current body mode, bookmark control, and page label at the foot
  of the reading paper. Bookmark persistence and pagination state are owned by
  the parent; this component emits only a save-bookmark intent.
-->
<script setup>
defineProps({
  bodyKind: { type: String, default: '' },
  pageLabel: { type: String, default: '' },
  readerMode: { type: String, default: 'empty' },
  savingBookmark: { type: Boolean, default: false },
})

defineEmits(['save-bookmark'])
</script>

<template>
  <footer class="paper-footer">
    <span>{{ bodyKind === 'annotated' ? 'Annotated' : 'Original' }}</span>
    <button
      v-if="readerMode === 'reading'"
      type="button"
      class="bookmark-save"
      :disabled="savingBookmark"
      @click="$emit('save-bookmark')"
    >{{ savingBookmark ? 'Saving...' : 'Bookmark' }}</button>
    <span>{{ pageLabel }}</span>
  </footer>
</template>
