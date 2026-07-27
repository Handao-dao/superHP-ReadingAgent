<!--
  Presents reader identity, view switching, connectivity, and page status.
  The parent coordinates reader, vocabulary, and recommendation views.
-->
<script setup>
defineProps({
  activeView: { type: String, default: 'reader' },
  bookTitle: { type: String, default: '' },
  chapterLabel: { type: String, default: '' },
  connected: { type: Boolean, default: false },
  pageLabel: { type: String, default: '' },
  paperTheme: { type: String, default: 'parchment' },
  paperThemeOpen: { type: Boolean, default: false },
})

defineEmits(['paper-theme-change', 'toggle-paper-theme', 'toggle-sidebar', 'view-change'])
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
        <button type="button" :class="{ 'is-active': activeView === 'recommendation' }" @click="$emit('view-change', 'recommendation')">选书</button>
      </div>
      <div class="paper-theme-control" @click.stop>
        <button
          type="button"
          class="paper-theme-trigger"
          :aria-expanded="paperThemeOpen"
          aria-haspopup="menu"
          @click="$emit('toggle-paper-theme')"
        >Paper: {{ paperTheme === 'white-paper' ? 'White' : 'Parchment' }}</button>
        <div v-if="paperThemeOpen" class="paper-theme-menu" role="menu">
          <button
            type="button"
            role="menuitemradio"
            :aria-checked="paperTheme === 'parchment'"
            :class="{ 'is-active': paperTheme === 'parchment' }"
            @click="$emit('paper-theme-change', 'parchment')"
          >Parchment</button>
          <button
            type="button"
            role="menuitemradio"
            :aria-checked="paperTheme === 'white-paper'"
            :class="{ 'is-active': paperTheme === 'white-paper' }"
            @click="$emit('paper-theme-change', 'white-paper')"
          >White Paper</button>
        </div>
      </div>
      <button type="button" class="catalog-toggle" @click="$emit('toggle-sidebar')">目录</button>
      <span class="status-pill" :class="{ 'is-online': connected }">{{ connected ? '在线' : '离线' }}</span>
      <span class="page-chip">{{ pageLabel }}</span>
    </div>
  </header>
</template>
