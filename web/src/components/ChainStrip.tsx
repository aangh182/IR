import { formatMs } from '../format'
import type { ChainHit, Hit } from '../types'
import { Icon } from './Icon'

type Props = {
  chain: ChainHit
  activeKfUid: number | null
  onSelect: (hit: Hit) => void
}

export function ChainStrip({ chain, activeKfUid, onSelect }: Props) {
  return (
    <section
      aria-label="Sự kiện trong chuỗi"
      className="mt-2 shrink-0 border-t border-slate-200 pt-2"
    >
      <div className="flex items-center justify-between gap-2 text-[10px] text-slate-500">
        <span className="min-w-0 truncate font-medium text-slate-600">
          Chuỗi sự kiện ·{' '}
          <span className="font-mono text-slate-900">{chain.video_id}</span>
        </span>
        <span className="shrink-0 font-mono tabular-nums">
          {chain.events.length} · {formatMs(chain.start_ms)}–{formatMs(chain.end_ms)}
        </span>
      </div>

      <div className="scroll-slim mt-1.5 flex gap-1.5 overflow-x-auto pb-1">
        {chain.events.map((event, index) => {
          const active = activeKfUid !== null && event.hit.kf_uid === activeKfUid
          return (
            <button
              key={`${event.hit.kf_uid ?? event.ts_ms}-${index}`}
              type="button"
              onClick={() => onSelect(event.hit)}
              aria-pressed={active}
              title={`Sự kiện ${index + 1} · ${formatMs(event.ts_ms)}`}
              className={`relative w-28 shrink-0 overflow-hidden rounded-lg border-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 focus-visible:ring-offset-[#f7f7f5] ${
                active
                  ? 'border-blue-600 ring-2 ring-blue-600/30'
                  : 'border-slate-200 hover:border-slate-400'
              }`}
            >
              <img
                src={event.hit.keyframe_url}
                alt=""
                loading="lazy"
                decoding="async"
                className="aspect-video w-full object-cover"
              />
              <span className="absolute left-1 top-1 flex h-4 w-4 items-center justify-center rounded bg-blue-600 font-mono text-[9px] font-bold text-white">
                {index + 1}
              </span>
              <span className="absolute inset-x-0 bottom-0 bg-slate-950/80 py-0.5 text-center font-mono text-[9px] text-white tabular-nums">
                {formatMs(event.ts_ms)}
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
    </section>
  )
}
