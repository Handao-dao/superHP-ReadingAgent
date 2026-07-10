<!--
  Presents reader identity, view switching, density selection, connectivity,
  and page status. It owns only the density menu's transient open/close state;
  the parent persists selections and coordinates reader or vocabulary views.
-->
<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps({
  activeView: { type: String, default: 'reader' },
  bookTitle: { type: String, default: '' },
  chapterLabel: { type: String, default: '' },
  connected: { type: Boolean, default: false },
  densityOptions: { type: Array, default: () => [] },
  isGenerating: { type: Boolean, default: false },
  pageLabel: { type: String, default: '' },
  selectedDensity: { type: String, default: 'M' },
})

const emit = defineEmits(['select-density', 'toggle-sidebar', 'view-change'])
const densityMenuOpen = ref(false)
const densityMenu = ref(null)

function toggleDensityMenu() {
  densityMenuOpen.value = !densityMenuOpen.value
}

function selectDensity(key) {
  emit('select-density', key)
  densityMenuOpen.value = false
}

function handleDocumentPointerdown(event) {
  if (!densityMenuOpen.value || densityMenu.value?.contains(event.target)) return
  densityMenuOpen.value = false
}

function handleKeydown(event) {
  if (event.key === 'Escape') densityMenuOpen.value = false
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerdown)
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerdown)
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <header class="reader-topbar">
    <div class="title-block">
      <p class="eyebrow">SuperHP Agent</p>
      <h1>{{ bookTitle || 'Reading Assistant' }}</h1>
      <p class="chapter-line">
        <span>{{ chapterLabel || 'Choose a reading action to begin' }}</span>
      </p>
    </div>

    <div class="session-cluster">
      <div class="view-switch" aria-label="页面切换">
        <button type="button" :class="{ 'is-active': activeView === 'reader' }" @click="$emit('view-change', 'reader')">阅读</button>
        <button type="button" :class="{ 'is-active': activeView === 'vocabulary' }" @click="$emit('view-change', 'vocabulary')">生词表</button>
      </div>
      <div ref="densityMenu" class="density-menu">
        <button
          type="button"
          class="density-trigger"
          :class="{ 'is-open': densityMenuOpen }"
          :disabled="isGenerating"
          aria-haspopup="menu"
          :aria-expanded="densityMenuOpen"
          @click="toggleDensityMenu"
        >Density: {{ selectedDensity }}</button>
        <div v-if="densityMenuOpen" class="density-options" role="menu">
          <button
            v-for="option in densityOptions"
            :key="option.key"
            type="button"
            role="menuitemradio"
            :aria-checked="selectedDensity === option.key"
            :class="{ 'is-active': selectedDensity === option.key }"
            @click="selectDensity(option.key)"
          >
            <strong>{{ option.key }}</strong>
            <span>{{ option.label }}</span>
          </button>
        </div>
      </div>
      <button type="button" class="catalog-toggle" @click="$emit('toggle-sidebar')">目录</button>
      <span class="status-pill" :class="{ 'is-online': connected }">{{ connected ? '在线' : '离线' }}</span>
      <span class="page-chip">{{ pageLabel }}</span>
    </div>
  </header>
</template>
