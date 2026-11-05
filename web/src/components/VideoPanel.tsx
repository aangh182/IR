import { useEffect, useRef, useState } from 'react'

import { formatMs } from '../format'
import type { Hit } from '../types'

type Props = {
  hit: Hit
}

function dresPayload(hit: Hit) {
  return {
    answerSets: [
      {
        answers: [
          {
            mediaItemName: hit.video_id,
            start: hit.start_ms,
            end: hit.end_ms,
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

  const payload = dresPayload(hit)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const seek = () => {
      video.currentTime = hit.start_ms / 1000
    }
    if (video.readyState >= 1) {
      seek()
    } else {
      video.addEventListener('loadedmetadata', seek, { once: true })
    }
    return () => video.removeEventListener('loadedmetadata', seek)
  }, [hit.video_id, hit.start_ms])

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
        src={hit.keyframe_url}
        alt={`${hit.video_id} @ ${formatMs(hit.start_ms)}`}
        className="aspect-video w-full rounded-xl border border-slate-800 object-cover"
      />

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
        <p className="text-xs text-slate-400">shot {hit.shot_idx}</p>
      </div>

      <dl className="grid grid-cols-3 gap-2 text-xs">
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
          <dt className="text-slate-500">Start</dt>
          <dd className="mt-1 font-mono text-slate-200">{formatMs(hit.start_ms)}</dd>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
          <dt className="text-slate-500">End</dt>
          <dd className="mt-1 font-mono text-slate-200">{formatMs(hit.end_ms)}</dd>
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
