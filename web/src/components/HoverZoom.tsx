import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const DELAY_MS = 250
const MAX_WIDTH = 560
const ASPECT = 9 / 16
const GAP = 12
const MARGIN = 12

type Position = {
  top: number
  left: number
  width: number
  height: number
}

function place(rect: DOMRect): Position {
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight
  const width = Math.min(MAX_WIDTH, viewportWidth - MARGIN * 2)
  const height = width * ASPECT

  let left = rect.right + GAP
  if (left + width > viewportWidth - MARGIN) {
    left = rect.left - width - GAP
  }
  left = Math.min(Math.max(MARGIN, left), viewportWidth - width - MARGIN)

  const top = Math.min(
    Math.max(MARGIN, rect.top + (rect.height - height) / 2),
    Math.max(MARGIN, viewportHeight - height - MARGIN),
  )

  return { top, left, width, height }
}

export function useHoverZoom<T extends HTMLElement>(src: string | null) {
  const anchorRef = useRef<T | null>(null)
  const timerRef = useRef<number | null>(null)
  const [position, setPosition] = useState<Position | null>(null)

  const clear = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const hide = useCallback(() => {
    clear()
    setPosition(null)
  }, [clear])

  useEffect(() => clear, [clear])

  useEffect(() => {
    if (!position) return
    window.addEventListener('scroll', hide, true)
    window.addEventListener('resize', hide)
    return () => {
      window.removeEventListener('scroll', hide, true)
      window.removeEventListener('resize', hide)
    }
  }, [position, hide])

  const show = useCallback(() => {
    const element = anchorRef.current
    if (!element || !src || timerRef.current !== null) return
    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return

    timerRef.current = window.setTimeout(() => {
      timerRef.current = null
      setPosition(place(element.getBoundingClientRect()))
    }, DELAY_MS)
  }, [src])

  const node =
    position && src
      ? createPortal(
          <div
            aria-hidden="true"
            className="hover-zoom pointer-events-none fixed z-50"
            style={{
              top: position.top,
              left: position.left,
              width: position.width,
              height: position.height,
            }}
          >
            <img
              src={src}
              alt=""
              decoding="async"
              className="h-full w-full rounded-xl border border-white/10 object-cover shadow-2xl shadow-slate-950/50"
            />
          </div>,
          document.body,
        )
      : null

  return { anchorRef, show, hide, node }
}
