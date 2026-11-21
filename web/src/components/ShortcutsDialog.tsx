import { useEffect, useRef } from 'react'

import { Icon } from './Icon'

const SHORTCUTS: { keys: string[]; label: string }[] = [
  { keys: ['/'], label: 'Tìm kiếm' },
  { keys: ['Enter'], label: 'Chạy truy vấn' },
  { keys: ['Shift', 'Enter'], label: 'Thêm sự kiện (chuỗi)' },
  { keys: ['↑', '↓', '←', '→'], label: 'Chọn frame' },
  { keys: ['Space'], label: 'Phát / dừng video' },
  { keys: ['[', ']'], label: 'Frame trước / sau' },
  { keys: ['S'], label: 'Nộp bài' },
  { keys: ['C'], label: 'Copy payload' },
  { keys: ['R'], label: 'Frame tương tự' },
  { keys: ['T'], label: 'Keyframe lân cận' },
  { keys: ['F'], label: 'Bộ lọc' },
  { keys: ['?'], label: 'Phím tắt' },
  { keys: ['Esc'], label: 'Đóng / quay lại' },
]

type Props = {
  open: boolean
  onClose: () => void
}

export function ShortcutsDialog({ open, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
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
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Đóng phím tắt"
        onClick={onClose}
        className="absolute inset-0 bg-slate-950/35 backdrop-blur-[1px]"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Phím tắt"
        className="relative w-full max-w-sm rounded-xl border border-slate-200 bg-white p-4 shadow-[0_24px_64px_-24px_rgba(15,23,42,0.5)]"
      >
        <div className="flex items-center justify-between gap-3 pb-3">
          <h2 className="text-sm font-semibold text-slate-900">Phím tắt</h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            className="flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
          >
            <Icon name="close" className="h-4 w-4" />
          </button>
        </div>
        <dl className="grid grid-cols-1 gap-x-4 gap-y-1.5 sm:grid-cols-2">
          {SHORTCUTS.map((item) => (
            <div key={item.label} className="flex items-center justify-between gap-2 py-0.5">
              <dt className="text-xs text-slate-600">{item.label}</dt>
              <dd className="flex shrink-0 items-center gap-1">
                {item.keys.map((key) => (
                  <kbd
                    key={key}
                    className="min-w-5 rounded border border-slate-200 bg-slate-50 px-1 py-0.5 text-center font-mono text-[10px] text-slate-600"
                  >
                    {key}
                  </kbd>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}
