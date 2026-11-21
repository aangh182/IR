import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

import { formatMs } from '../format'
import type { Hit, SearchResponse } from '../types'
import { Icon } from './Icon'

type Props = {
  videoId: string
  activeKfUid: number | null
  onSelect: (hit: Hit) => void
}

const KEYFRAME_CACHE = new Map<string, Hit[]>()
const KEYFRAME_CACHE_LIMIT = 8

async function fetchKeyframes(videoId: string): Promise<Hit[]> {
  const cached = KEYFRAME_CACHE.get(videoId)
  if (cached) return cached

  const response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/keyframes`)
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // use the HTTP status
    }
    throw new Error(detail)
  }
  const data = (await response.json()) as SearchResponse
  KEYFRAME_CACHE.set(videoId, data.results)
  if (KEYFRAME_CACHE.size > KEYFRAME_CACHE_LIMIT) {
    const oldest = KEYFRAME_CACHE.keys().next().value
    if (oldest !== undefined) KEYFRAME_CACHE.delete(oldest)
  }
  return data.results
}

function keyframeTs(hit: Hit): number {
  return hit.frames.find((frame) => frame.is_keyframe)?.ts_ms ?? hit.start_ms
}

export function VideoKeyframeStrip({ videoId, activeKfUid, onSelect }: Props) {
  const [keyframes, setKeyframes] = useState<Hit[]>(
    () => KEYFRAME_CACHE.get(videoId) ?? [],
  )
  const [loading, setLoading] = useState(() => !KEYFRAME_CACHE.has(videoId))
  const [error, setError] = useState<string | null>(null)
  const stripRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchKeyframes(videoId)
      .then((data) => {
        if (!cancelled) setKeyframes(data)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [videoId])

  useEffect(() => {
    if (activeKfUid === null) return
    const target = document.querySelector(`[data-video-kf="${activeKfUid}"]`)
    target?.scrollIntoView({ block: 'nearest', inline: 'center' })
  }, [activeKfUid, keyframes.length])

  useEffect(() => {
    const element = stripRef.current
    if (!element) return
    const strip = element

    function onWheel(event: WheelEvent) {
      if (strip.scrollWidth <= strip.clientWidth) return
      const delta =
        Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX
      if (delta === 0) return
      const atStart = strip.scrollLeft <= 0
      const atEnd = strip.scrollLeft + strip.clientWidth >= strip.scrollWidth - 1
      if ((delta < 0 && atStart) || (delta > 0 && atEnd)) return
      event.preventDefault()
      strip.scrollLeft += delta
    }

    strip.addEventListener('wheel', onWheel, { passive: false })
    return () => strip.removeEventListener('wheel', onWheel)
  }, [keyframes.length])

  function handleStripKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    event.stopPropagation()
    const current = keyframes.findIndex((hit) => hit.kf_uid === activeKfUid)
    const base = current === -1 ? 0 : current
    const next = Math.max(
      0,
      Math.min(
        keyframes.length - 1,
        base + (event.key === 'ArrowRight' ? 1 : -1),
      ),
    )
    if (next === current) return
    onSelect(keyframes[next])
  }

  return (
    <section
      aria-label={`Toàn bộ keyframe của ${videoId}`}
      className="mt-3 shrink-0 border-t border-slate-200 pt-2"
    >
      <div className="flex items-center justify-between gap-2 pb-1.5">
        <h3 className="min-w-0 truncate text-[11px] font-medium text-slate-600">
          Toàn bộ keyframe · <span className="font-mono text-slate-900">{videoId}</span>
        </h3>
        <span className="shrink-0 font-mono text-[10px] text-slate-500 tabular-nums">
          {loading ? '...' : `${keyframes.length} frame`}
        </span>
      </div>

      {loading ? (
        <div className="flex gap-1.5 overflow-hidden pb-1" aria-busy="true">
          {Array.from({ length: 12 }).map((_, index) => (
            <div
              key={index}
              className="h-11 w-20 shrink-0 animate-pulse rounded-md bg-slate-200/70"
            />
          ))}
        </div>
      ) : error ? (
        <p className="py-2 text-[11px] text-red-700">{error}</p>
      ) : keyframes.length === 0 ? (
        <p className="py-2 text-[11px] text-slate-500">Video chưa có keyframe.</p>
      ) : (
        <div
          ref={stripRef}
          tabIndex={0}
          onKeyDown={handleStripKeyDown}
          aria-label="Timeline keyframe; dùng ← → để chọn"
          className="scroll-slim flex gap-1.5 overflow-x-auto rounded-md pb-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/50"
        >
          {keyframes.map((hit) => {
            const active = hit.kf_uid !== null && hit.kf_uid === activeKfUid
            const ts = keyframeTs(hit)
            return (
              <button
                key={hit.kf_uid ?? `${hit.video_id}-${hit.shot_idx}-${hit.start_ms}`}
                type="button"
                data-video-kf={hit.kf_uid ?? undefined}
                onClick={() => onSelect(hit)}
                aria-pressed={active}
                title={`${formatMs(ts)} · shot ${hit.shot_idx}`}
                className={`relative w-20 shrink-0 overflow-hidden rounded-md border-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 focus-visible:ring-offset-[#f7f7f5] ${
                  active
                    ? 'border-blue-600 ring-2 ring-blue-600/40'
                    : 'border-slate-200 hover:border-slate-400'
                }`}
              >
                <img
                  src={hit.keyframe_url}
                  alt=""
                  loading="lazy"
                  decoding="async"
                  className="aspect-video w-full object-cover"
                />
                {active && (
                  <span
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-0 bg-blue-500/10"
                  />
                )}
                <span
                  className={`absolute inset-x-0 bottom-0 py-0.5 text-center font-mono text-[9px] tabular-nums ${
                    active ? 'bg-blue-600 font-semibold text-white' : 'bg-slate-950/80 text-white'
                  }`}
                >
                  {formatMs(ts)}
                </span>
                {active && (
                  <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-blue-600 text-white">
                    <Icon name="check" className="h-2.5 w-2.5" />
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}
