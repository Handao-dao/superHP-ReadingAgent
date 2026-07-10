/**
 * Owns annotation density choices, persisted selection, and the backend level
 * mapped from each UI key. It does not trigger annotation actions or decide
 * which reading unit receives the selected density.
 */
import { computed, ref } from 'vue'

const DENSITY_STORAGE_KEY = 'superhp_annotation_density'
const DEFAULT_DENSITY = 'M'

export function useAnnotationDensity() {
  const densityOptions = [
    { key: 'H', label: 'High', level: 'beginner' },
    { key: 'M', label: 'Medium', level: 'intermediate' },
    { key: 'L', label: 'Low', level: 'advanced' },
  ]
  const storedDensity = localStorage.getItem(DENSITY_STORAGE_KEY) || DEFAULT_DENSITY
  const selectedDensity = ref(
    densityOptions.some((option) => option.key === storedDensity) ? storedDensity : DEFAULT_DENSITY,
  )
  const selectedLevel = computed(() => {
    return densityOptions.find((option) => option.key === selectedDensity.value)?.level || 'intermediate'
  })

  function selectDensity(key) {
    selectedDensity.value = densityOptions.some((option) => option.key === key) ? key : DEFAULT_DENSITY
    localStorage.setItem(DENSITY_STORAGE_KEY, selectedDensity.value)
  }

  return {
    densityOptions,
    selectDensity,
    selectedDensity,
    selectedLevel,
  }
}
