import { useEffect } from 'react'

import type { ModelInfo, ObjectFilter } from '../types'
import { Icon } from './Icon'

const TOP_K_OPTIONS = [20, 30, 50]

type Props = {
  open: boolean
  onClose: () => void
  models: ModelInfo[]
  selectedModel: string
  onModelChange: (model: string) => void
  topK: number
  onTopKChange: (value: number) => void
  includeBoilerplate: boolean
  onBoilerplateChange: (value: boolean) => void
  dedup: boolean
  onDedupChange: (value: boolean) => void
  objectFilters: ObjectFilter[]
  onRemoveObject: (label: string) => void
  onOpenObjects: () => void
  onReset: () => void
  isDefault: boolean
}

export function FilterPopover({
  open,
  onClose,
  models,
  selectedModel,
  onModelChange,
  topK,
  onTopKChange,
  includeBoilerplate,
  onBoilerplateChange,
  dedup,
  onDedupChange,
  objectFilters,
  onRemoveObject,
  onOpenObjects,
  onReset,
  isDefault,
}: Props) {
  useEffect(() => {
    if (!open) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Đóng bộ lọc"
        onClick={onClose}
        className="absolute inset-0 bg-slate-950/10"
      />
      <div
        role="dialog"
        aria-modal="false"
        aria-label="Bộ lọc tìm kiếm"
        className="absolute right-3 top-16 max-h-[calc(100dvh-5rem)] w-[min(360px,calc(100vw-24px))] overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 shadow-[0_16px_40px_-16px_rgba(15,23,42,0.35)] sm:right-5"
      >
        <div className="flex items-center justify-between gap-3 pb-3">
          <h2 className="text-sm font-semibold text-slate-900">Bộ lọc</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            className="flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
          >
            <Icon name="close" className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4">
          <label htmlFor="filter-model" className="block">
            <span className="text-[10px] font-medium text-slate-500">Mô hình</span>
            <select
              id="filter-model"
              value={selectedModel}
              onChange={(event) => onModelChange(event.target.value)}
              className="mt-1 h-9 w-full rounded-lg border border-slate-200 bg-white px-2.5 text-sm text-slate-800 outline-none transition-colors focus:border-blue-600 focus:ring-2 focus:ring-blue-600/15"
            >
              {models.length === 0 && <option value="">(default)</option>}
              {models.map((item) => (
                <option key={item.name} value={item.name} disabled={!item.available}>
                  {item.name} · {item.dim}d{item.available ? '' : ' · chưa có index'}
                </option>
              ))}
            </select>
          </label>

          <div>
            <span className="text-[10px] font-medium text-slate-500">Số kết quả</span>
            <div className="mt-1 flex rounded-lg border border-slate-200 p-0.5">
              {TOP_K_OPTIONS.map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => onTopKChange(value)}
                  aria-pressed={topK === value}
                  className={`flex-1 rounded-md px-2 py-1.5 text-xs font-medium tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 ${
                    topK === value
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  {value}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-medium text-slate-500">Vật thể (COCO)</span>
              <button
                type="button"
                onClick={onOpenObjects}
                className="text-[11px] font-medium text-blue-700 transition-colors hover:text-blue-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
              >
                Chọn nhãn
              </button>
            </div>
            {objectFilters.length > 0 ? (
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {objectFilters.map((item) => (
                  <li
                    key={item.label}
                    className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 py-0.5 pl-2 pr-1 text-[11px] text-blue-900"
                  >
                    <span className="max-w-32 truncate font-medium">{item.label}</span>
                    <span className="font-mono text-[10px] text-blue-700/80 tabular-nums">
                      ≥{item.minCount}
                    </span>
                    <button
                      type="button"
                      onClick={() => onRemoveObject(item.label)}
                      aria-label={`Bỏ ${item.label}`}
                      className="flex h-4 w-4 items-center justify-center rounded-full text-blue-700/70 transition-colors hover:bg-white hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
                    >
                      <Icon name="close" className="h-2.5 w-2.5" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-[11px] text-slate-500">Không lọc vật thể</p>
            )}
          </div>

          <div className="space-y-1.5 border-t border-slate-100 pt-3">
            <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg px-1 py-1.5">
              <span className="text-xs text-slate-700">Hiện intro/logo</span>
              <input
                type="checkbox"
                checked={includeBoilerplate}
                onChange={(event) => onBoilerplateChange(event.target.checked)}
                className="h-4 w-4 accent-blue-600"
              />
            </label>
            <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg px-1 py-1.5">
              <span className="text-xs text-slate-700">Bỏ ảnh gần trùng</span>
              <input
                type="checkbox"
                checked={dedup}
                onChange={(event) => onDedupChange(event.target.checked)}
                className="h-4 w-4 accent-blue-600"
              />
            </label>
          </div>

          {!isDefault && (
            <div className="border-t border-slate-100 pt-3">
              <button
                type="button"
                onClick={onReset}
                className="text-[11px] font-medium text-slate-500 transition-colors hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
              >
                Đặt lại bộ lọc
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
