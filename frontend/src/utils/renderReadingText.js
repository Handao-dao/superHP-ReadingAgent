const escapeHtml = (value = '') => {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function inlineMarkup(text = '') {
  return escapeHtml(text).replace(
    /\[\[(.+?)\|(.+?)\]\]/g,
    (_, word, translation) => {
      const safeWord = escapeHtml(word)
      const safeTranslation = escapeHtml(translation)
      return `<span class="vocab-word" data-word="${safeWord}">${safeWord}</span><span class="translation">(${safeTranslation})</span>`
    }
  )
}

export function splitReadingBlocks(raw = '') {
  return String(raw || '')
    .replace(/\r\n/g, '\n')
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean)
}

export function splitLongBlock(text, limit) {
  if (text.length <= limit) return [text]
  const sentences = text.split(/(?<=[.!?。！？])\s+/).filter(Boolean)
  if (sentences.length <= 1) return chunkText(text, limit)

  const chunks = []
  let current = ''
  for (const sentence of sentences) {
    const candidate = current ? `${current} ${sentence}` : sentence
    if (candidate.length > limit && current) {
      chunks.push(current)
      current = sentence
    } else {
      current = candidate
    }
  }
  if (current) chunks.push(current)
  return chunks.flatMap((chunk) => chunk.length > limit ? chunkText(chunk, limit) : [chunk])
}

function chunkText(text, limit) {
  const chunks = []
  for (let index = 0; index < text.length; index += limit) {
    chunks.push(text.slice(index, index + limit))
  }
  return chunks
}

export function renderReadingBlock(block = '') {
  const heading = block.match(/^(#{1,6})\s+(.+)$/)
  if (heading) {
    const level = Math.min(3, heading[1].length + 1)
    return `<h${level}>${inlineMarkup(heading[2])}</h${level}>`
  }

  const html = block
    .split('\n')
    .map((line) => inlineMarkup(line.trim()))
    .filter(Boolean)
    .join('<br>')

  return `<p>${html}</p>`
}