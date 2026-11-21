import { formatMs } from '../format'
import type { ChainHit } from '../types'
import { Icon } from './Icon'

type Props = {
  chain: ChainHit
  selected: boolean
  onSelect: (chain: ChainHit) => void
}

export function ChainCard({ chain, selected, onSelect }: Props) {
  const events = chain.events.slice(0, 4)
  return (
    <button
      type="button"
      data-chain-key={`${chain.video_id}-${chain.start_ms}-${chain.score.toFixed(4)}`}
      onClick={() => onSelect(chain)}
      title={
        chain.collapsed
          ? 'Các sự kiện gần nhau; chọn frame trong clip'
          : 'Chuỗi sự kiện theo thời gian'
      }
      aria-pressed={selected}
      aria-label={`${chain.video_id}, ${chain.events.length} sự kiện, ${formatMs(chain.start_ms)}`}
      className={`group relative block w-full overflow-hidden rounded-xl border-2 bg-slate-100 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 focus-visible:ring-offset-[#f7f7f5] ${
        selected
          ? 'border-blue-600 ring-2 ring-blue-600/50 ring-offset-2 ring-offset-[#f7f7f5]'
          : 'border-slate-200 hover:border-slate-400'
      }`}
    >
      <div className="flex gap-0.5 overflow-hidden">
        {events.map((event, index) => (
          <div
            key={`${event.hit.kf_uid ?? event.ts_ms}-${index}`}
            className="relative min-w-0 flex-1"
          >
            <img
              src={event.hit.keyframe_url}
              alt=""
              loading="lazy"
              decoding="async"
              className="aspect-video h-full w-full object-cover"
            />
            <span className="absolute left-1 top-1 flex h-4 w-4 items-center justify-center rounded bg-blue-600 font-mono text-[9px] font-bold text-white">
              {index + 1}
            </span>
            <span className="absolute inset-x-0 bottom-0 truncate bg-slate-950/80 px-1 py-0.5 text-center font-mono text-[9px] text-white tabular-nums">
              {formatMs(event.ts_ms)}
            </span>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between gap-2 p-2">
        <div className="min-w-0">
          <p className="truncate font-mono text-[11px] font-semibold text-slate-900">
            {chain.video_id}
          </p>
          <p className="truncate text-[10px] text-slate-500">
            {chain.collapsed ? 'gộp · ' : ''}
            {chain.events.length} sự kiện · {formatMs(chain.start_ms)}–{formatMs(chain.end_ms)}
          </p>
        </div>
        <span className="shrink-0 font-mono text-[10px] text-slate-500 tabular-nums">
          {chain.score.toFixed(3)}
        </span>
      </div>

      {selected && (
        <span className="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-white">
          <Icon name="check" className="h-3 w-3" />
        </span>
      )}
    </button>
  )
}
