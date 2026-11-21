import { useRef } from 'react'

import { formatMs } from '../format'
import type { Hit } from '../types'
import { Icon } from './Icon'

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
      data-hit-key={`${hit.video_id}-${hit.shot_idx}-${hit.kf_uid ?? hit.start_ms}`}
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
      title="Chọn frame · Ctrl/Cmd + click: tìm tương tự · Shift + click: xem lân cận"
      aria-pressed={selected}
      aria-current={selected ? 'true' : undefined}
      aria-label={`${hit.video_id}, ${formatMs(displayTs)}, điểm ${hit.score.toFixed(4)}${selected ? ', đang chọn' : ''}`}
      className={`group relative block w-full overflow-hidden rounded-xl border-2 bg-slate-100 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 focus-visible:ring-offset-[#f7f7f5] ${
        selected
          ? 'border-blue-600 ring-2 ring-blue-600/50 ring-offset-2 ring-offset-[#f7f7f5]'
          : 'border-slate-200 hover:border-slate-400'
      }`}
    >
      <div className="relative aspect-video overflow-hidden">
        <img
          src={hit.keyframe_url}
          alt=""
          loading="lazy"
          decoding="async"
          className="h-full w-full object-cover"
        />

        {selected && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 bg-blue-500/10"
          />
        )}

        <span
          className={`absolute bottom-1.5 left-1.5 max-w-[calc(100%-3rem)] truncate rounded px-1.5 py-0.5 font-mono text-[10px] leading-tight backdrop-blur-sm ${
            selected
              ? 'bg-blue-600 font-semibold text-white'
              : 'bg-slate-950/75 text-white'
          }`}
        >
          {hit.video_id} · {formatMs(displayTs)}
        </span>

        {showScore && (
          <span
            className={`absolute right-1.5 top-1.5 rounded px-1.5 py-0.5 font-mono text-[10px] leading-tight tabular-nums backdrop-blur-sm ${
              selected
                ? 'bg-blue-600 font-semibold text-white'
                : 'bg-slate-950/75 text-white'
            }`}
          >
            {hit.score.toFixed(4)}
          </span>
        )}

        {hit.is_boilerplate && !selected && (
          <span className="absolute left-1.5 top-1.5 rounded bg-amber-500 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-amber-950">
            B
          </span>
        )}

        {selected && (
          <span className="absolute bottom-1.5 right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-white shadow-sm">
            <Icon name="check" className="h-3 w-3" />
          </span>
        )}
      </div>
    </button>
  )
}
