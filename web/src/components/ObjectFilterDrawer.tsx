import { useEffect, useMemo, useRef, useState } from 'react'

import type { ObjectFacet, ObjectFilter } from '../types'
import { Icon } from './Icon'

type Props = {
  open: boolean
  facets: ObjectFacet[]
  filters: ObjectFilter[]
  onClose: () => void
  onApply: () => void
  onChange: (next: ObjectFilter[]) => void
}

function clampCount(value: number): number {
  if (!Number.isFinite(value)) return 1
  return Math.min(99, Math.max(1, Math.round(value)))
}

function compactCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`
  if (value >= 10_000) return `${Math.round(value / 1_000)}k`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  return String(value)
}

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'

export function ObjectFilterDrawer({
  open,
  facets,
  filters,
  onClose,
  onApply,
  onChange,
}: Props) {
  const [search, setSearch] = useState('')
  const panelRef = useRef<HTMLElement | null>(null)
  const closeRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!open) return
    const previouslyFocused = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !panelRef.current) return
      const items = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((element) => element.offsetParent !== null)
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      previouslyFocused?.focus?.()
    }
  }, [open, onClose])

  const groups = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const byCategory = new Map<string, ObjectFacet[]>()
    for (const facet of facets) {
      if (
        needle &&
        !facet.label.includes(needle) &&
        !facet.category.toLowerCase().includes(needle)
      ) {
        continue
      }
      const list = byCategory.get(facet.category) ?? []
      list.push(facet)
      byCategory.set(facet.category, list)
    }
    return [...byCategory.entries()]
  }, [facets, search])

  const selected = useMemo(
    () => new Map(filters.map((item) => [item.label, item.minCount])),
    [filters],
  )

  function toggle(label: string) {
    if (selected.has(label)) {
      onChange(filters.filter((item) => item.label !== label))
    } else {
      onChange([...filters, { label, minCount: 1 }])
    }
  }

  function setMinCount(label: string, value: number) {
    onChange(
      filters.map((item) =>
        item.label === label ? { ...item, minCount: clampCount(value) } : item,
      ),
    )
  }

  return (
    <div
      className={`fixed inset-0 z-50 ${open ? '' : 'pointer-events-none'}`}
      aria-hidden={!open}
      inert={!open}
    >
      <button
        type="button"
        aria-label="Đóng bộ lọc object"
        onClick={onClose}
        className={`absolute inset-0 bg-slate-950/35 transition-opacity duration-200 ease-out motion-reduce:transition-none ${
          open ? 'opacity-100' : 'opacity-0'
        }`}
      />

      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="object-filter-title"
        className={`absolute left-0 top-0 flex h-full w-full max-w-md flex-col bg-white shadow-[24px_0_48px_-24px_rgba(15,23,42,0.35)] transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none sm:rounded-r-2xl ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-4">
          <div className="min-w-0">
            <h2
              id="object-filter-title"
              className="text-base font-semibold tracking-tight text-slate-900"
            >
              Vật thể (COCO)
            </h2>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Số lượng tối thiểu mỗi nhãn trong frame.
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition-colors hover:border-slate-300 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
          >
            <Icon name="close" className="h-4 w-4" />
          </button>
        </header>

        <section aria-label="Tag đang lọc" className="border-b border-slate-200 px-4 py-3">
          <div className="flex items-center gap-2">
            <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Đang lọc
            </h3>
            {filters.length > 0 && (
              <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-blue-100 px-1 font-mono text-[9px] font-semibold text-blue-800 tabular-nums">
                {filters.length}
              </span>
            )}
          </div>

          {filters.length === 0 ? (
            <p className="mt-2 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-2.5 text-[11px] text-slate-500">
              Chưa chọn nhãn.
            </p>
          ) : (
            <ul className="scroll-slim mt-2 max-h-52 divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
              {filters.map((item) => (
                <li key={item.label} className="flex items-center gap-2.5 px-2.5 py-1.5">
                  <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-600" />
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-slate-900">
                    {item.label}
                  </span>
                  <div
                    className="flex shrink-0 items-center overflow-hidden rounded-md border border-slate-200"
                    title="Số lượng tối thiểu trong frame"
                  >
                    <button
                      type="button"
                      aria-label={`Giảm ${item.label}`}
                      onClick={() => setMinCount(item.label, item.minCount - 1)}
                      disabled={item.minCount <= 1}
                      className="h-8 w-8 border-r border-slate-200 font-mono text-xs text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-600/60 disabled:cursor-not-allowed disabled:text-slate-300"
                    >
                      −
                    </button>
                    <input
                      type="number"
                      min={1}
                      max={99}
                      value={item.minCount}
                      aria-label={`Số lượng tối thiểu ${item.label} trong frame`}
                      onChange={(event) => setMinCount(item.label, Number(event.target.value))}
                      className="h-8 w-10 appearance-none border-0 bg-transparent text-center font-mono text-xs text-slate-900 caret-blue-600 outline-none focus:bg-blue-50/60 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                    />
                    <button
                      type="button"
                      aria-label={`Tăng ${item.label}`}
                      onClick={() => setMinCount(item.label, item.minCount + 1)}
                      disabled={item.minCount >= 99}
                      className="h-8 w-8 border-l border-slate-200 font-mono text-xs text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-600/60 disabled:cursor-not-allowed disabled:text-slate-300"
                    >
                      +
                    </button>
                  </div>
                  <button
                    type="button"
                    aria-label={`Bỏ ${item.label}`}
                    onClick={() => toggle(item.label)}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
                  >
                    <Icon name="close" className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="border-b border-slate-200 px-4 py-2.5">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Tìm nhãn hoặc nhóm..."
            autoComplete="off"
            spellCheck={false}
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 caret-blue-600 outline-none transition-colors placeholder:text-slate-500 focus:border-blue-600 focus:ring-2 focus:ring-blue-600/15"
          />
        </div>

        <div className="scroll-slim min-h-0 flex-1 overflow-y-auto">
          <div className="px-4 pb-4">
            {facets.length === 0 ? (
              <p className="mt-3 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-[11px] text-slate-500">
                Chưa có nhãn vật thể. Import shard trước.
              </p>
            ) : groups.length === 0 ? (
              <p className="mt-3 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-6 text-center text-[11px] text-slate-500">
                Không có nhãn nào khớp “{search.trim()}”.
              </p>
            ) : (
              groups.map(([category, items]) => {
                const activeCount = items.filter((item) => selected.has(item.label)).length
                return (
                  <section key={category} className="pt-3">
                    <div className="sticky top-0 z-10 -mx-4 flex items-baseline justify-between gap-2 border-b border-slate-100 bg-white px-4 pb-1.5 pt-2">
                      <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                        {category}
                      </h3>
                      {activeCount > 0 && (
                        <span className="font-mono text-[10px] text-blue-700 tabular-nums">
                          {activeCount}/{items.length}
                        </span>
                      )}
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {items.map((facet) => {
                        const active = selected.has(facet.label)
                        return (
                          <button
                            key={facet.label}
                            type="button"
                            onClick={() => toggle(facet.label)}
                            aria-pressed={active}
                            title={`${facet.keyframes.toLocaleString('vi-VN')} keyframe · ${facet.videos.toLocaleString('vi-VN')} video`}
                            className={`rounded-full border px-2.5 py-1.5 text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 ${
                              active
                                ? 'border-blue-600 bg-blue-50 font-medium text-blue-900'
                                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
                            }`}
                          >
                            {facet.label}
                            <span
                              aria-hidden="true"
                              className={`ml-1 font-mono text-[9px] tabular-nums ${
                                active ? 'text-blue-700/80' : 'text-slate-500'
                              }`}
                            >
                              {compactCount(facet.keyframes)}
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  </section>
                )
              })
            )}
          </div>
        </div>

        <footer className="flex items-center gap-3 border-t border-slate-200 px-4 py-3">
          <p className="min-w-0 flex-1 truncate text-[11px] text-slate-500">
            {filters.length === 0 ? 'Không lọc vật thể' : `${filters.length} nhãn · khớp tất cả`}
          </p>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => onChange([])}
              disabled={filters.length === 0}
              className="whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 disabled:cursor-not-allowed disabled:text-slate-300"
            >
              Xoá hết
            </button>
            <button
              type="button"
              onClick={onApply}
              className="whitespace-nowrap rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2"
            >
              Áp dụng
            </button>
          </div>
        </footer>
      </aside>
    </div>
  )
}
