export function formatMs(value: number): string {
  const safe = Math.max(0, value)
  const seconds = Math.floor(safe / 1000)
  const minutes = Math.floor(seconds / 60)
  const remainderSeconds = seconds % 60
  const milliseconds = safe % 1000
  return `${String(minutes).padStart(2, '0')}:${String(remainderSeconds).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`
}
