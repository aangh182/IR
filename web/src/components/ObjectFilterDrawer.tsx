import { useEffect, useMemo, useRef, useState } from 'react'

import type { ObjectFacet, ObjectFilter } from '../types'

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

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 12 12"
      aria-hidden="true"
      className="h-3 w-3"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    >
      <path d="M3 3l6 6M9 3l-6 6" />
    </svg>
  )
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
        className={`absolute inset-0 bg-slate-950/45 transition-opacity duration-200 ease-out motion-reduce:transition-none ${
          open ? 'opacity-100' : 'opacity-0'
        }`}
      />

      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="object-filter-title"
        className={`absolute left-0 top-0 flex h-full w-full max-w-md flex-col bg-[#fbfaf7] shadow-[24px_0_48px_-24px_rgba(15,23,42,0.35)] transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] selection:bg-amber-200/70 selection:text-slate-900 sm:rounded-r-2xl motion-reduce:transition-none ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-4">
          <div className="min-w-0">
            <h2
              id="object-filter-title"
              className="text-base font-semibold tracking-tight text-slate-900"
            >
              Object (COCO)
            </h2>
            <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
              Số lượng tối thiểu của mỗi tag trong frame.
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-600 transition hover:border-slate-400 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40"
          >
            Đóng
          </button>
        </header>

        <section aria-label="Tag đang lọc" className="border-b border-slate-200 px-4 py-3">
          <div className="flex items-center gap-2">
            <h3 className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-600">
              Tag đang lọc
            </h3>
            {filters.length > 0 && (
              <span
                aria-hidden="true"
                className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500/15 px-1 font-mono text-[9px] font-semibold tabular-nums text-amber-800"
              >
                {filters.length}
              </span>
            )}
          </div>

          {filters.length === 0 ? (
            <p className="mt-2 rounded-lg border border-dashed border-slate-300 bg-white/70 px-3 py-2.5 text-[11px] leading-relaxed text-slate-500">
              Chưa chọn tag. Bấm một tag bên dưới để thêm.
            </p>
          ) : (
            <ul className="scroll-slim mt-2 max-h-52 divide-y divide-slate-200 overflow-y-auto rounded-lg border border-slate-200 bg-white">
              {filters.map((item) => (
                <li key={item.label} className="flex items-center gap-2.5 px-2.5 py-1.5">
                  <span
                    aria-hidden="true"
                    className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500"
                  />
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-slate-900">
                    {item.label}
                  </span>
                  <div
                    className="flex shrink-0 items-center overflow-hidden rounded-md border border-slate-300 bg-white"
                    title="Số lượng tối thiểu trong frame"
                  >
                    <button
                      type="button"
                      aria-label={`Giảm ${item.label}`}
                      onClick={() => setMinCount(item.label, item.minCount - 1)}
                      disabled={item.minCount <= 1}
                      className="h-8 w-8 border-r border-slate-200 font-mono text-xs text-slate-600 transition hover:bg-slate-50 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-amber-500/40 disabled:cursor-not-allowed disabled:text-slate-300"
                    >
                      −
                    </button>
                    <input
                      type="number"
                      min={1}
                      max={99}
                      value={item.minCount}
                      aria-label={`Số lượng tối thiểu ${item.label} trong frame`}
                      onChange={(event) =>
                        setMinCount(item.label, Number(event.target.value))
                      }
                      className="h-8 w-10 [appearance:textfield] border-0 bg-transparent text-center font-mono text-xs tabular-nums text-slate-900 caret-amber-600 outline-none focus:bg-amber-50/60 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                    />
                    <button
                      type="button"
                      aria-label={`Tăng ${item.label}`}
                      onClick={() => setMinCount(item.label, item.minCount + 1)}
                      disabled={item.minCount >= 99}
                      className="h-8 w-8 border-l border-slate-200 font-mono text-xs text-slate-600 transition hover:bg-slate-50 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-amber-500/40 disabled:cursor-not-allowed disabled:text-slate-300"
                    >
                      +
                    </button>
                  </div>
                  <button
                    type="button"
                    aria-label={`Bỏ ${item.label}`}
                    onClick={() => toggle(item.label)}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition hover:bg-white hover:text-rose-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40"
                  >
                    <CloseIcon />
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
            placeholder="Tìm tag hoặc nhóm..."
            autoComplete="off"
            spellCheck={false}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 caret-amber-600 outline-none transition placeholder:text-slate-500 focus:border-amber-500 focus:ring-2 focus:ring-amber-500/15"
          />
        </div>

        <div className="scroll-slim min-h-0 flex-1 overflow-y-auto">
          <div className="px-4 pb-4">
            {facets.length === 0 ? (
              <p className="mt-3 rounded-lg border border-dashed border-slate-300 bg-white/70 px-3 py-3 text-[11px] leading-relaxed text-slate-500">
                Chưa có object tag. Import shard trước:{' '}
                <code className="font-mono text-slate-700">
                  uv run ir import-objects &lt;zip&gt;
                </code>
              </p>
            ) : groups.length === 0 ? (
              <p className="mt-3 rounded-lg border border-dashed border-slate-300 bg-white/70 px-3 py-6 text-center text-[11px] text-slate-500">
                Không có tag nào khớp “{search.trim()}”.
              </p>
            ) : (
              groups.map(([category, items]) => {
                const activeCount = items.filter((item) =>
                  selected.has(item.label),
                ).length
                return (
                  <section key={category} className="pt-3">
                    <div className="sticky top-0 z-10 -mx-4 flex items-baseline justify-between gap-2 border-b border-slate-200/80 bg-[#fbfaf7] px-4 pb-1.5 pt-2">
                      <h3 className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-600">
                        {category}
                      </h3>
                      {activeCount > 0 && (
                        <span
                          aria-hidden="true"
                          className="font-mono text-[10px] tabular-nums text-amber-800"
                        >
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
                            className={`rounded-full border px-2.5 py-1.5 text-[11px] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40 ${
                              active
                                ? 'border-amber-500 bg-amber-500/10 font-medium text-amber-900'
                                : 'border-slate-300 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900'
                            }`}
                          >
                            {facet.label}
                            <span
                              aria-hidden="true"
                              className={`ml-1 font-mono text-[9px] tabular-nums ${
                                active ? 'text-amber-700/80' : 'text-slate-500'
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
            {filters.length === 0
              ? 'Không lọc object'
              : `${filters.length} tag · khớp tất cả`}
          </p>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => onChange([])}
              disabled={filters.length === 0}
              className="whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-600 transition hover:border-slate-400 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40 disabled:cursor-not-allowed disabled:text-slate-400"
            >
              Xoá hết
            </button>
            <button
              type="button"
              onClick={onApply}
              className="whitespace-nowrap rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white transition hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900/40 focus-visible:ring-offset-2 focus-visible:ring-offset-[#fbfaf7]"
            >
              Áp dụng
            </button>
          </div>
        </footer>
      </aside>
    </div>
  )
}
