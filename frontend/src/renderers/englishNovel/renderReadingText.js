const escapeHtml = (value = '') => {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

const normalizeWord = (word = '') => String(word).trim().toLowerCase()

function renderWord(word, options = {}) {
  const key = normalizeWord(word)
  const hidden = options.hiddenAnnotations?.has(key)
  const manualTranslation = options.manualAnnotations?.get(key)
  const safeWord = escapeHtml(word)
  if (manualTranslation && !hidden) {
    const safeTranslation = escapeHtml(manualTranslation)
    return `<span class="vocab-word is-manual" data-word="${safeWord}" data-translation="${safeTranslation}">${safeWord}</span><span class="translation">(${safeTranslation})</span>`
  }
  return `<span class="text-word" data-word="${safeWord}">${safeWord}</span>`
}

function renderPlainText(text = '', options = {}) {
  return String(text)
    .split(/([A-Za-z][A-Za-z'’-]*)/g)
    .map((part) => {
      if (/^[A-Za-z][A-Za-z'’-]*$/.test(part)) return renderWord(part, options)
      return escapeHtml(part)
    })
    .join('')
}

function renderAnnotatedWord(word, translation, pos = '', options = {}) {
  const key = normalizeWord(word)
  if (options.hiddenAnnotations?.has(key)) return renderPlainText(word, options)
  const safeWord = escapeHtml(word)
  const safeTranslation = escapeHtml(translation)
  const safePos = escapeHtml(pos)
  const posAttr = safePos ? ` data-pos="${safePos}"` : ''
  return `<span class="vocab-word" data-word="${safeWord}" data-translation="${safeTranslation}"${posAttr}>${safeWord}</span><span class="translation">(${safeTranslation})</span>`
}

function inlineMarkup(text = '', options = {}) {
  const marker = /\[\[([^|\]]+)\|([^|\]]+)(?:\|([^|\]]+))?\]\]/g
  let html = ''
  let lastIndex = 0
  for (const match of String(text).matchAll(marker)) {
    html += renderPlainText(String(text).slice(lastIndex, match.index), options)
    html += renderAnnotatedWord(match[1], match[2], match[3] || '', options)
    lastIndex = match.index + match[0].length
  }
  html += renderPlainText(String(text).slice(lastIndex), options)
  return html
}

export function splitReadingBlocks(raw = '') {
  return String(raw || '')
    .replace(/\r\n/g, '\n')
    .replace(/<!--[\s\S]*?-->/g, '')
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean)
}

export function renderReadingBlock(block = '', options = {}) {
  const heading = block.match(/^(#{1,6})\s+(.+)$/)
  if (heading) {
    const level = Math.min(3, heading[1].length + 1)
    return `<h${level}>${inlineMarkup(heading[2], options)}</h${level}>`
  }

  const html = block
    .split('\n')
    .map((line) => inlineMarkup(line.trim(), options))
    .filter(Boolean)
    .join('<br>')

  return `<p>${html}</p>`
}

