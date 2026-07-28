<!--
  Presents one manual reading Episode without owning HTTP or reader state.
  Closing the drawer is local; “结束本轮” closes and summarizes the Episode.
-->
<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  canRetry: { type: Boolean, default: false },
  canSend: { type: Boolean, default: false },
  contextChanged: { type: Boolean, default: false },
  currentMeta: { type: Object, default: null },
  errorCode: { type: String, default: '' },
  errorMessage: { type: String, default: '' },
  hasSession: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  lastSummary: { type: String, default: '' },
  messages: { type: Array, default: () => [] },
  open: { type: Boolean, default: false },
  selectedText: { type: String, default: '' },
  session: { type: Object, default: null },
})

const emit = defineEmits(['clear-selection', 'close', 'end', 'new-session', 'retry', 'send'])
const draft = ref('')
const transcript = ref(null)
const composer = ref(null)

const activeQuote = computed(() => (
  props.hasSession
    ? String(props.session?.selected_text || '').trim()
    : props.selectedText.trim()
))
const hasNewSelection = computed(() => (
  props.hasSession
  && props.selectedText.trim()
  && props.selectedText.trim() !== String(props.session?.selected_text || '').trim()
))
const canSubmit = computed(() => (
  Boolean(props.currentMeta?.id)
  && !props.contextChanged
  && !props.loading
  && (!props.hasSession || props.canSend)
))

const quickQuestions = computed(() => {
  const questions = [
    '这个人物以前出现过吗？',
    '帮我回顾一下此前发生的重要事情。',
    '这个词在之前的章节里出现过吗？',
  ]
  if (props.selectedText.trim()) {
    questions.unshift('结合上下文，这段话应该怎样理解？')
  }
  return questions
})

function submitMessage() {
  const message = draft.value.trim()
  if (!message || !canSubmit.value) return
  draft.value = ''
  emit('send', message)
}

function useQuickQuestion(question) {
  draft.value = question
  nextTick(() => composer.value?.focus())
}

async function scrollToLatest() {
  await nextTick()
  if (transcript.value) {
    transcript.value.scrollTop = transcript.value.scrollHeight
  }
}

watch(
  () => [props.messages.length, props.loading, props.open],
  scrollToLatest,
  { flush: 'post' },
)
</script>

<template>
  <button
    v-if="open"
    type="button"
    class="companion-scrim"
    aria-label="关闭阅读助手"
    @click="$emit('close')"
  ></button>

  <aside
    class="companion-drawer"
    :class="{ 'is-open': open }"
    role="dialog"
    aria-modal="true"
    aria-label="阅读助手对话"
    :aria-hidden="!open"
  >
    <header class="companion-header">
      <div>
        <p class="small-label">Reading companion</p>
        <h2>阅读助手</h2>
        <p v-if="currentMeta">
          {{ currentMeta.book_title }} · Chapter {{ currentMeta.chapter_no }}
        </p>
        <p v-else>打开一章正文后即可开始交流</p>
      </div>
      <button type="button" class="companion-close" aria-label="关闭" @click="$emit('close')">×</button>
    </header>

    <div v-if="contextChanged" class="companion-context-notice" role="status">
      <strong>当前对话属于另一章节</strong>
      <span>为避免混淆检索范围，请为现在的章节开启一轮新对话。</span>
      <button type="button" :disabled="loading" @click="$emit('new-session')">切换到当前章节</button>
    </div>

    <div v-else-if="hasNewSelection" class="companion-context-notice" role="status">
      <strong>检测到新的选中文本</strong>
      <span>当前后端只在一轮对话开始时冻结选段，可以用这段文字开启新对话。</span>
      <button type="button" :disabled="loading" @click="$emit('new-session')">基于新选段开始</button>
    </div>

    <blockquote v-if="activeQuote" class="companion-selection">
      <div>
        <span>{{ hasSession ? '本轮选段' : '准备带入本轮的选段' }}</span>
        <button
          v-if="!hasSession"
          type="button"
          aria-label="清除选段"
          @click="$emit('clear-selection')"
        >清除</button>
      </div>
      <p>{{ activeQuote }}</p>
    </blockquote>

    <div ref="transcript" class="companion-transcript" aria-live="polite">
      <section v-if="!hasSession" class="companion-welcome">
        <span class="companion-mark">R</span>
        <h3>{{ currentMeta ? '聊聊正在读的内容' : '还没有打开正文' }}</h3>
        <p v-if="currentMeta">
          可以直接提问，也可以先在正文中选中一段文字。只有发送第一条消息时才会真正调用助手。
        </p>
        <p v-else>请先从目录打开一章原文或译注。</p>
        <div v-if="currentMeta" class="companion-quick-questions">
          <button
            v-for="question in quickQuestions"
            :key="question"
            type="button"
            @click="useQuickQuestion(question)"
          >{{ question }}</button>
        </div>
      </section>

      <template v-else>
        <article
          v-for="(message, index) in messages"
          :key="`${message.role}-${index}-${message.content.slice(0, 20)}`"
          class="companion-message"
          :class="`is-${message.role}`"
        >
          <span>{{ message.role === 'assistant' ? '阅读助手' : '你' }}</span>
          <p>{{ message.content }}</p>
        </article>
      </template>

      <div v-if="loading" class="companion-thinking" role="status">
        <i></i><i></i><i></i>
        <span>正在结合阅读上下文思考</span>
      </div>
    </div>

    <p v-if="errorMessage" class="companion-error" role="alert">{{ errorMessage }}</p>

    <div v-if="!hasSession && lastSummary" class="companion-context-notice" role="status">
      <strong>上一轮已整理为长期记忆</strong>
      <span>{{ lastSummary }}</span>
    </div>

    <div v-if="hasSession && canRetry" class="companion-retry" role="status">
      <span>
        {{ errorCode === 'invalid_model_response'
          ? '助手没有返回有效内容，原消息已保留。'
          : '模型服务暂时没有响应，原消息已保留。' }}
      </span>
      <button type="button" :disabled="loading" @click="$emit('retry')">
        {{ loading ? '正在重试…' : '重新尝试' }}
      </button>
    </div>

    <form
      v-if="currentMeta && !contextChanged"
      class="companion-composer"
      @submit.prevent="submitMessage"
    >
      <label for="reading-companion-message">
        {{ hasSession ? '继续提问' : '向阅读助手提问' }}
      </label>
      <textarea
        id="reading-companion-message"
        ref="composer"
        v-model="draft"
        :disabled="loading || (hasSession && !canSend)"
        maxlength="4000"
        placeholder="例如：这个人物之前在哪里出现过？"
        rows="3"
        @keydown.ctrl.enter.prevent="submitMessage"
      ></textarea>
      <div>
        <span>Ctrl + Enter 发送</span>
        <span class="companion-composer-actions">
          <button
            v-if="hasSession"
            type="button"
            class="is-secondary"
            :disabled="loading"
            @click="$emit('end')"
          >结束本轮</button>
          <button type="submit" :disabled="!canSubmit || !draft.trim()">发送</button>
        </span>
      </div>
    </form>
  </aside>
</template>
