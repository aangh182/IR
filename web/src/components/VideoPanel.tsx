import { useEffect, useRef, useState } from 'react'

import { formatMs } from '../format'
import type { FrameOption, Hit } from '../types'

type Props = {
  hit: Hit
  onActiveFrameChange?: (frame: FrameOption) => void
}

function framesOf(hit: Hit): FrameOption[] {
  if (hit.frames.length > 0) return hit.frames
  return [
    {
      ts_ms: hit.start_ms,
      start_ms: hit.start_ms,
      end_ms: hit.end_ms,
      url: hit.keyframe_url,
      is_keyframe: true,
    },
  ]
}

function dresPayload(hit: Hit, frame: FrameOption) {
  return {
    answerSets: [
      {
        answers: [
          {
            mediaItemName: hit.video_id,
            start: frame.ts_ms,
            end: frame.ts_ms,
          },
        ],
      },
    ],
  }
}

export function VideoPanel({ hit, onActiveFrameChange }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [copied, setCopied] = useState(false)
  const [videoError, setVideoError] = useState(false)
  const [activeIdx, setActiveIdx] = useState<number | null>(null)

  const frames = framesOf(hit)
  const keyframeIdx = Math.max(
    0,
    frames.findIndex((frame) => frame.is_keyframe),
  )
  const activeIndex = Math.min(activeIdx ?? keyframeIdx, frames.length - 1)
  const active = frames[activeIndex]
  const offsetMs = active.ts_ms - frames[keyframeIdx].ts_ms
  const offsetLabel =
    offsetMs === 0 ? 'keyframe' : `${offsetMs > 0 ? '+' : ''}${offsetMs} ms`

  const payload = dresPayload(hit, active)

  useEffect(() => {
    onActiveFrameChange?.(active)
  }, [active, onActiveFrameChange])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const seek = () => {
      video.currentTime = active.ts_ms / 1000
    }
    if (video.readyState >= 1) {
      seek()
    } else {
      video.addEventListener('loadedmetadata', seek, { once: true })
    }
    return () => video.removeEventListener('loadedmetadata', seek)
  }, [hit.video_id, active.ts_ms])

  async function copyPayload() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-3">
      <div className="relative overflow-hidden rounded-lg border border-slate-200 bg-slate-900">
        <img
          src={active.url}
          alt={`${hit.video_id} @ ${formatMs(active.ts_ms)}`}
          className="aspect-video w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-slate-950/75 to-transparent" />
        <div className="absolute inset-x-2 bottom-2 flex items-end justify-between gap-2">
          <span className="rounded bg-slate-950/80 px-1.5 py-0.5 font-mono text-[10px] text-slate-200 backdrop-blur">
            {formatMs(active.ts_ms)}
          </span>
          <span className="rounded bg-slate-950/75 px-1.5 py-0.5 font-mono text-[10px] text-slate-400 backdrop-blur">
            {offsetLabel}
          </span>
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.16em] text-slate-500">
          <span>{frames.length} frame</span>
          <span className="font-mono tracking-normal">
            {activeIndex + 1}/{frames.length}
          </span>
        </div>
        <div className="scroll-slim flex gap-2 overflow-x-auto pb-1">
          {frames.map((frame, index) => (
            <button
              key={`${frame.ts_ms}-${index}`}
              type="button"
              onClick={() => setActiveIdx(index)}
              aria-pressed={index === activeIndex}
              title={formatMs(frame.ts_ms)}
              className={`relative w-20 shrink-0 overflow-hidden rounded-md border transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40 ${
                index === activeIndex
                  ? 'border-amber-500'
                  : 'border-slate-300 hover:border-slate-400'
              }`}
            >
              <img
                src={frame.url}
                alt={formatMs(frame.ts_ms)}
                loading="lazy"
                className="aspect-video w-full object-cover"
              />
              <span className="absolute inset-x-0 bottom-0 bg-slate-950/80 py-0.5 text-center font-mono text-[9px] text-slate-200">
                {formatMs(frame.ts_ms)}
              </span>
              {frame.is_keyframe && (
                <span className="absolute left-1 top-1 rounded bg-amber-500 px-1 text-[9px] font-semibold text-slate-950">
                  key
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-black">
        <video
          key={hit.video_id}
          ref={videoRef}
          controls
          playsInline
          preload="metadata"
          onError={() => setVideoError(true)}
          className="aspect-video w-full bg-black"
          src={`/api/videos/${encodeURIComponent(hit.video_id)}/stream`}
        />
      </div>

      {videoError && (
        <p className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">
          Không stream được video này. Kiểm tra file gốc còn trong `minibatch/` không.
        </p>
      )}

      <dl className="grid grid-cols-3 gap-2 text-[11px]">
        <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1.5">
          <dt className="text-slate-500">Start</dt>
          <dd className="mt-0.5 font-mono text-slate-900">{formatMs(active.start_ms)}</dd>
        </div>
        <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1.5">
          <dt className="text-slate-500">End</dt>
          <dd className="mt-0.5 font-mono text-slate-900">{formatMs(active.end_ms)}</dd>
        </div>
        <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1.5">
          <dt className="text-slate-500">Score</dt>
          <dd className="mt-0.5 font-mono text-amber-700">{hit.score.toFixed(4)}</dd>
        </div>
      </dl>

      <button
        type="button"
        onClick={() => void copyPayload()}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-xs font-semibold text-slate-700 transition hover:border-amber-500 hover:text-amber-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40"
      >
        {copied ? 'Đã copy payload' : 'Copy DRES payload'}
      </button>

      <details className="rounded-lg border border-slate-200 bg-slate-50">
        <summary className="cursor-pointer select-none px-3 py-2 text-[11px] text-slate-600">
          Payload DRES
        </summary>
        <pre className="max-h-40 overflow-auto border-t border-slate-200 p-3 font-mono text-[10px] leading-relaxed text-slate-600">
          {JSON.stringify(payload, null, 2)}
        </pre>
      </details>
    </section>
  )
}
