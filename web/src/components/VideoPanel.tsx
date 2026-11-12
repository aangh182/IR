import { useEffect, useRef, useState } from 'react'

import { formatMs } from '../format'
import type { FrameOption, Hit } from '../types'

type Props = {
  hit: Hit
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
            start: frame.start_ms,
            end: frame.end_ms,
          },
        ],
      },
    ],
  }
}

export function VideoPanel({ hit }: Props) {
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
    <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <img
        src={active.url}
        alt={`${hit.video_id} @ ${formatMs(active.ts_ms)}`}
        className="aspect-video w-full rounded-xl border border-slate-800 object-cover"
      />

      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>{frames.length} frame</span>
          <span className="font-mono">
            {activeIndex + 1}/{frames.length} · {offsetLabel}
          </span>
        </div>
        <div className="flex gap-2 overflow-x-auto pb-1">
          {frames.map((frame, index) => (
            <button
              key={`${frame.ts_ms}-${index}`}
              type="button"
              onClick={() => setActiveIdx(index)}
              title={formatMs(frame.ts_ms)}
              className={`relative w-20 shrink-0 overflow-hidden rounded-lg border transition ${
                index === activeIndex
                  ? 'border-indigo-400'
                  : 'border-slate-700 hover:border-slate-500'
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
                <span className="absolute left-1 top-1 rounded bg-indigo-500/90 px-1 text-[9px] font-semibold text-white">
                  key
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-800 bg-black">
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
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          Không stream được video này. Kiểm tra file gốc còn trong `minibatch/` không.
        </p>
      )}

      <div>
        <p className="font-mono text-lg font-semibold text-slate-100">{hit.video_id}</p>
        <p className="text-xs text-slate-400">
          shot {hit.shot_idx} · {formatMs(hit.start_ms)} → {formatMs(hit.end_ms)}
        </p>
      </div>

      <dl className="grid grid-cols-3 gap-2 text-xs">
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
          <dt className="text-slate-500">Start</dt>
          <dd className="mt-1 font-mono text-slate-200">{formatMs(active.start_ms)}</dd>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
          <dt className="text-slate-500">End</dt>
          <dd className="mt-1 font-mono text-slate-200">{formatMs(active.end_ms)}</dd>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
          <dt className="text-slate-500">Score</dt>
          <dd className="mt-1 font-mono text-slate-200">{hit.score.toFixed(4)}</dd>
        </div>
      </dl>

      <button
        type="button"
        onClick={() => void copyPayload()}
        className="w-full rounded-lg bg-indigo-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-400"
      >
        {copied ? 'Đã copy payload' : 'Copy DRES payload'}
      </button>

      <pre className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/80 p-3 font-mono text-[11px] leading-relaxed text-slate-400">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </div>
  )
}
