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
    .replace(/<!--[\s\S]*?-->/g, '')
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean)
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
