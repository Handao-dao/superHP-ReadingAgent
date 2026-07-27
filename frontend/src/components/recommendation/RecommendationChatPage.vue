<!--
  Presents the recommendation transcript, request states, and verified books.
  Session persistence and HTTP side effects are owned by useRecommendationSession.
-->
<script setup>
import { nextTick, ref, watch } from 'vue'
import RecommendationBookCard from './RecommendationBookCard.vue'

const props = defineProps({
  canSend: { type: Boolean, default: false },
  errorMessage: { type: String, default: '' },
  hasSession: { type: Boolean, default: false },
  hasStoredSession: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  messages: { type: Array, default: () => [] },
  phase: { type: String, default: '' },
  recommendedBooks: { type: Array, default: () => [] },
})

const emit = defineEmits(['restore', 'send', 'start'])
const draft = ref('')
const transcript = ref(null)

const phaseLabels = {
  collecting_preferences: '了解偏好',
  searching: '检索书目',
  awaiting_user: '等待回复',
  completed: '推荐完成',
  failed: '暂时中断',
}

function submitMessage() {
  const message = draft.value.trim()
  if (!message || !props.canSend) return
  draft.value = ''
  emit('send', message)
}

async function scrollToLatest() {
  await nextTick()
  if (transcript.value) {
    transcript.value.scrollTop = transcript.value.scrollHeight
  }
}

watch(
  () => [props.messages.length, props.loading, props.recommendedBooks.length],
  scrollToLatest,
  { flush: 'post' },
)
</script>

<template>
  <section class="recommendation-chat">
    <header class="recommendation-chat-header">
      <div>
        <p class="small-label">Book Match</p>
        <h2>找到适合持续阅读的下一本书</h2>
        <p>通过简短对话了解题材偏好和阅读感受，再从本地图书目录中给出建议。</p>
      </div>
      <span v-if="phase" class="recommendation-phase" :data-phase="phase">
        {{ phaseLabels[phase] || phase }}
      </span>
    </header>

    <div ref="transcript" class="recommendation-transcript" aria-live="polite">
      <div v-if="!hasSession" class="recommendation-welcome">
        <span class="recommendation-welcome-mark">R</span>
        <h3>从一次轻松的选书对话开始</h3>
        <p>助手会询问少量偏好，并只推荐本地目录中能够验证难度和题材的图书。</p>
        <button
          type="button"
          :disabled="loading"
          @click="$emit(hasStoredSession ? 'restore' : 'start')"
        >
          {{ loading ? '正在准备…' : hasStoredSession ? '重新恢复对话' : '开始选书' }}
        </button>
      </div>

      <template v-else>
        <article
          v-for="(message, index) in messages"
          :key="`${message.role}-${index}-${message.content.slice(0, 20)}`"
          class="recommendation-message"
          :class="`is-${message.role}`"
        >
          <span>{{ message.role === 'assistant' ? '选书助手' : '你' }}</span>
          <p>{{ message.content }}</p>
        </article>

        <div v-if="loading" class="recommendation-thinking" role="status">
          <i></i><i></i><i></i>
          <span>正在思考并核对书目</span>
        </div>

        <section v-if="recommendedBooks.length" class="recommendation-results">
          <div class="recommendation-results-heading">
            <p class="small-label">Verified suggestions</p>
            <h3>本次推荐</h3>
          </div>
          <div class="recommendation-book-grid">
            <RecommendationBookCard
              v-for="book in recommendedBooks"
              :key="book.catalog_id"
              :book="book"
            />
          </div>
          <p class="recommendation-next-step">
            推荐已经完成。你可以从左侧书库选择对应图书，进入现有阅读与标注流程。
          </p>
        </section>
      </template>
    </div>

    <p v-if="errorMessage" class="recommendation-error" role="alert">
      {{ errorMessage }}
    </p>

    <form
      v-if="hasSession && phase === 'awaiting_user'"
      class="recommendation-composer"
      @submit.prevent="submitMessage"
    >
      <label for="recommendation-message">回复选书助手</label>
      <div>
        <textarea
          id="recommendation-message"
          v-model="draft"
          :disabled="loading"
          maxlength="4000"
          placeholder="例如：我喜欢轻松一点的侦探故事，也愿意接受少量生词。"
          rows="2"
          @keydown.ctrl.enter.prevent="submitMessage"
        ></textarea>
        <button type="submit" :disabled="!canSend || !draft.trim()">
          发送
        </button>
      </div>
      <span>Ctrl + Enter 发送</span>
    </form>

    <div v-else-if="hasSession && phase === 'completed'" class="recommendation-complete">
      本轮选书对话已经完成。后续阅读数据达到困难触发条件时，系统会征求你的意见，再重新唤醒这段对话。
    </div>
  </section>
</template>
