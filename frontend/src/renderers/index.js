import { classicalChineseRenderer } from './classicalChinese'
import { englishNovelRenderer } from './englishNovel'

const fallbackRenderer = englishNovelRenderer

const renderers = {
  english_novel: englishNovelRenderer,
  classical_chinese: classicalChineseRenderer,
}

export function getReadingRenderer(profileId = '') {
  return renderers[profileId] || fallbackRenderer
}
