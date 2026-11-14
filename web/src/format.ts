export function formatMs(value: number): string {
  const safe = Math.max(0, value)
  const seconds = Math.floor(safe / 1000)
  const minutes = Math.floor(seconds / 60)
  const remainderSeconds = seconds % 60
  const milliseconds = safe % 1000
  return `${String(minutes).padStart(2, '0')}:${String(remainderSeconds).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`
}

export function parseTimestamp(input: string): number | null {
  const value = input.trim()
  if (!value) return null

  if (/^\d+$/.test(value)) return Number(value)

  const clock = value.match(/^(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?$/)
  if (clock) {
    const [, hours, minutes, seconds, fraction = ''] = clock
    return (
      Number(hours ?? 0) * 3_600_000 +
      Number(minutes) * 60_000 +
      Number(seconds) * 1000 +
      Number(fraction.padEnd(3, '0'))
    )
  }

  const float = Number(value)
  return Number.isFinite(float) ? Math.round(float) : null
}
