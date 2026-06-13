import { englishNovelRenderer } from './englishNovel'

const fallbackRenderer = englishNovelRenderer

const renderers = {
  english_novel: englishNovelRenderer,
}

export function getReadingRenderer(profileId = '') {
  return renderers[profileId] || fallbackRenderer
}

