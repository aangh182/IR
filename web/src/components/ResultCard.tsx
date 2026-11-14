import { useRef } from 'react'

import { formatMs } from '../format'
import type { Hit } from '../types'

type Props = {
  hit: Hit
  selected: boolean
  showScore?: boolean
  onSelect: (hit: Hit) => void
  onSimilar: (hit: Hit) => void
  onTimeline: (hit: Hit) => void
}

export function ResultCard({
  hit,
  selected,
  showScore = true,
  onSelect,
  onSimilar,
  onTimeline,
}: Props) {
  const similarAt = useRef(0)
  const keyframe = hit.frames.find((frame) => frame.is_keyframe)
  const displayTs = keyframe?.ts_ms ?? hit.start_ms

  function triggerSimilar() {
    const now = Date.now()
    if (now - similarAt.current < 300) return
    similarAt.current = now
    onSimilar(hit)
  }

  return (
    <button
      type="button"
      data-kf-uid={hit.kf_uid ?? undefined}
      onClick={(event) => {
        if (event.shiftKey) {
          event.preventDefault()
          onTimeline(hit)
          return
        }
        if (event.ctrlKey || event.metaKey) {
          event.preventDefault()
          triggerSimilar()
          return
        }
        onSelect(hit)
      }}
      onContextMenu={(event) => {
        if (event.ctrlKey || event.metaKey) {
          event.preventDefault()
          triggerSimilar()
        }
      }}
      title="Shift + click: timeline · Ctrl/Cmd + click: tìm tương tự"
      aria-pressed={selected}
      className={`group relative overflow-hidden rounded-lg border text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40 focus-visible:ring-offset-2 focus-visible:ring-offset-[#f5f3ee] ${
        selected
          ? 'border-amber-500 bg-amber-50/60 ring-1 ring-amber-500/20'
          : 'border-slate-200 bg-white hover:border-slate-400'
      }`}
    >
      <div className="relative aspect-video overflow-hidden bg-slate-900">
        <img
          src={hit.keyframe_url}
          alt={`${hit.video_id} @ ${formatMs(displayTs)}`}
          loading="lazy"
          className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-slate-950/85 via-slate-950/0 to-slate-950/10" />

        {showScore && (
          <span className="absolute right-2 top-2 rounded border border-white/10 bg-slate-950/75 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-300 backdrop-blur">
            {hit.score.toFixed(4)}
          </span>
        )}

        {hit.is_boilerplate && (
          <span className="absolute left-2 top-2 rounded bg-rose-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
            boilerplate
          </span>
        )}

        <div className="absolute inset-x-2 bottom-2 flex items-end justify-between gap-2">
          <span className="rounded bg-slate-950/80 px-1.5 py-0.5 font-mono text-[10px] text-slate-200 backdrop-blur">
            {formatMs(displayTs)}
          </span>
          <span className="rounded bg-slate-950/70 px-1.5 py-0.5 font-mono text-[10px] text-slate-400 backdrop-blur">
            shot {hit.shot_idx}
          </span>
        </div>
      </div>

      <div className="space-y-1.5 p-2.5">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate font-mono text-[11px] text-slate-900">{hit.video_id}</p>
          <span className="shrink-0 font-mono text-[10px] text-slate-500">
            {formatMs(hit.end_ms - hit.start_ms)}
          </span>
        </div>

        {hit.evidence.objects.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {hit.evidence.objects.slice(0, 5).map((label) => (
              <span
                key={label}
                className="rounded bg-slate-100 px-1 py-0.5 text-[10px] text-slate-600"
              >
                {label}
              </span>
            ))}
          </div>
        )}
      </div>

      {selected && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-amber-500" />}
    </button>
  )
}
