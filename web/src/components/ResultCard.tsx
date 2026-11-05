import { formatMs } from '../format'
import type { Hit } from '../types'

type Props = {
  hit: Hit
  selected: boolean
  onSelect: (hit: Hit) => void
}

export function ResultCard({ hit, selected, onSelect }: Props) {
  return (
    <button
      type="button"
      onClick={() => onSelect(hit)}
      className={`group overflow-hidden rounded-xl border text-left transition ${
        selected
          ? 'border-indigo-400 bg-indigo-500/10'
          : 'border-slate-800 bg-slate-900/60 hover:border-slate-600'
      }`}
    >
      <div className="relative aspect-video overflow-hidden bg-slate-950">
        <img
          src={hit.keyframe_url}
          alt={`${hit.video_id} @ ${formatMs(hit.start_ms)}`}
          loading="lazy"
          className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.02]"
        />
        <span className="absolute bottom-2 left-2 rounded bg-slate-950/80 px-2 py-0.5 font-mono text-[11px] text-slate-200">
          {formatMs(hit.start_ms)}
        </span>
        <span className="absolute right-2 top-2 rounded bg-indigo-500/90 px-2 py-0.5 font-mono text-[11px] font-semibold text-white">
          {hit.score.toFixed(4)}
        </span>
      </div>
      <div className="space-y-1 p-3">
        <p className="truncate font-mono text-sm text-slate-100">{hit.video_id}</p>
        <p className="text-xs text-slate-400">
          shot {hit.shot_idx} · {formatMs(hit.start_ms)} → {formatMs(hit.end_ms)}
        </p>
      </div>
    </button>
  )
}
