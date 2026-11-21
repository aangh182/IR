const PREFIXED = /^l\s*(\d{1,3})\s*[_\-\s]?\s*v\s*(\d{1,3})$/i
const BARE_SPACE = /^(\d{1,3})\s+(\d{1,3})$/
const BARE_SEPARATED = /^(\d{1,3})[_-](\d{1,3})$/

export function normalizeVideoShorthand(input: string): string | null {
  const value = input.trim()
  if (!value) return null

  const match = value.match(PREFIXED) ?? value.match(BARE_SPACE) ?? value.match(BARE_SEPARATED)
  if (!match) return null

  const part = Number(match[1])
  const number = Number(match[2])
  if (!Number.isInteger(part) || !Number.isInteger(number)) return null
  if (part < 1 || part > 99 || number < 1 || number > 999) return null

  return `L${String(part).padStart(2, '0')}_V${String(number).padStart(3, '0')}`
}

const ARROW_SPLIT = /\s*(?:→|->|=>|\r?\n)\s*/
const CONNECTOR_SPLIT =
  /\s*(?:;|mở đầu|đầu tiên|sau đó|tiếp theo|kế tiếp|cuối cùng|kết thúc|rồi)\s*/i

export function splitSequence(input: string): string[] {
  const value = input.trim()
  if (!value) return []

  const direct = value
    .split(ARROW_SPLIT)
    .map((part) => part.trim())
    .filter(Boolean)
  if (direct.length >= 2) return direct.slice(0, 6)

  return value
    .split(CONNECTOR_SPLIT)
    .map((part) => part.trim())
    .filter(Boolean)
    .slice(0, 6)
}
