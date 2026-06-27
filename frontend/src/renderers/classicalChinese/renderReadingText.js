const escapeHtml = (value = '') => {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

const normalizeKey = (word = '') => String(word).trim().toLowerCase()

function renderPlainText(text = '') {
  return escapeHtml(text)
}

function renderAnnotatedWord(word, translation, pos = '', options = {}) {
  const key = normalizeKey(word)
  if (options.hiddenAnnotations?.has(key)) return renderPlainText(word)
  const safeWord = escapeHtml(word)
  const safeTranslation = escapeHtml(translation)
  const safePos = escapeHtml(pos)
  const posAttr = safePos ? ` data-pos="${safePos}"` : ''
  return (
    `<span class="classical-annotation" data-word="${safeWord}" data-translation="${safeTranslation}"${posAttr}>` +
    `<span class="classical-word">${safeWord}</span>` +
    `<span class="classical-gloss">${safeTranslation}</span>` +
    `</span>`
  )
}

function inlineMarkup(text = '', options = {}) {
  const marker = /\[\[([^|\]]+)\|([^|\]]+)(?:\|([^|\]]+))?\]\]/g
  let html = ''
  let lastIndex = 0
  for (const match of String(text).matchAll(marker)) {
    html += renderPlainText(String(text).slice(lastIndex, match.index))
    html += renderAnnotatedWord(match[1], match[2], match[3] || '', options)
    lastIndex = match.index + match[0].length
  }
  html += renderPlainText(String(text).slice(lastIndex))
  return html
}

export function splitReadingBlocks(raw = '') {
  const blocks = String(raw || '')
    .replace(/\r\n/g, '\n')
    .replace(/<!--[\s\S]*?-->/g, '')
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean)

  const result = []
  for (let index = 0; index < blocks.length; index += 1) {
    const block = blocks[index]
    const next = blocks[index + 1]
    if (/^#{1,6}\s+.+$/.test(block) && isAuthorLine(next)) {
      result.push(`${block}\n@author ${next}`)
      index += 1
    } else {
      result.push(block)
    }
  }
  return result
}

export function renderReadingBlock(block = '', options = {}) {
  const titleWithAuthor = block.match(/^(#{1,6})\s+(.+)\n@author\s+(.+)$/)
  if (titleWithAuthor) {
    const level = Math.min(3, titleWithAuthor[1].length + 1)
    return (
      `<h${level} class="classical-heading classical-heading-with-author">` +
      `${inlineMarkup(titleWithAuthor[2], options)}` +
      `<span class="classical-author">${inlineMarkup(titleWithAuthor[3], options)}</span>` +
      `</h${level}>`
    )
  }

  const heading = block.match(/^(#{1,6})\s+(.+)$/)
  if (heading) {
    const level = Math.min(3, heading[1].length + 1)
    return `<h${level} class="classical-heading">${inlineMarkup(heading[2], options)}</h${level}>`
  }

  const html = block
    .split('\n')
    .map((line) => inlineMarkup(line.trim(), options))
    .filter(Boolean)
    .join('<br>')

  return `<p class="classical-paragraph">${html}</p>`
}

function isAuthorLine(block = '') {
  const text = String(block || '').trim()
  if (!text || text.includes('\n')) return false
  if (/[。！？；：，、,.!?;:]/.test(text)) return false
  return text.length <= 12
}
