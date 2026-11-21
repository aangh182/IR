import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import type { DresQuery } from '../types'
import { Icon } from './Icon'

type Props = {
  onUseQuery: (query: string) => void
  refreshKey: number
  sequential: boolean
}

async function fetchQuery(): Promise<DresQuery> {
  const response = await fetch('/api/dres/query')
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // use the HTTP status
    }
    throw new Error(detail)
  }
  return (await response.json()) as DresQuery
}

export function ExamQueryDock({ onUseQuery, refreshKey, sequential }: Props) {
  const [data, setData] = useState<DresQuery | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const closeRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    let active = true
    const load = () => {
      fetchQuery()
        .then((body) => {
          if (!active) return
          setData(body)
          setError(null)
        })
        .catch((err: Error) => {
          if (active) setError(err.message)
        })
    }
    load()
    const timer = window.setInterval(load, 15000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [refreshKey])

  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        setOpen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [open])

  const query = data?.query ?? ''
  const segments = data?.segments ?? []
  const queryText =
    sequential && segments.length > 0 ? segments.join(' → ') : query
  const message = error ?? data?.error ?? null
  const evaluationName = data?.evaluation_name ?? ''
  const taskLabel = data?.task_name
    ? `${data.task_name}${data.task_group ? ` · ${data.task_group}` : ''}`
    : (data?.task_status ?? '')
  const timeLeft = data?.time_left != null ? `${data.time_left}s` : ''
  const summary = [evaluationName, taskLabel, timeLeft].filter(Boolean).join(' · ')

  async function copy() {
    if (!queryText) return
    try {
      await navigator.clipboard.writeText(queryText)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard unavailable
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={summary || 'Query đề thi'}
        className="flex h-9 min-w-0 max-w-[320px] items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 text-left transition-colors hover:border-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
      >
        <Icon name="document" className="h-4 w-4 shrink-0 text-slate-500" />
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-[10px] font-medium leading-tight text-slate-500">
            Query đề thi
          </span>
          <span className="truncate text-[11px] font-medium leading-tight text-slate-800">
            {summary || (data?.configured === false ? 'DRES chưa cấu hình' : 'Chưa có query')}
          </span>
        </span>
        <span className="shrink-0 text-[10px] font-medium text-blue-700">Mở</span>
      </button>

      {open &&
        createPortal(
          <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
            <button
              type="button"
              aria-label="Đóng query đề thi"
              onClick={() => setOpen(false)}
              className="absolute inset-0 bg-slate-950/35 backdrop-blur-[1px]"
            />
            <div
              role="dialog"
              aria-modal="true"
              aria-label="Query đề thi"
              className="relative flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-[0_24px_64px_-24px_rgba(15,23,42,0.5)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold text-slate-900">Query đề thi</h2>
                  <p className="mt-0.5 truncate text-[11px] text-slate-500">
                    {summary || 'Chưa có query'}
                  </p>
                </div>
                <button
                  ref={closeRef}
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Đóng"
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
                >
                  <Icon name="close" className="h-4 w-4" />
                </button>
              </div>

              <div className="scroll-slim mt-3 min-h-0 flex-1 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3">
                {message ? (
                  <p className="text-xs leading-relaxed text-red-700">{message}</p>
                ) : segments.length > 0 ? (
                  <div className="space-y-2">
                    {segments.map((segment, index) => (
                      <p
                        key={index}
                        className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800"
                      >
                        {segment}
                      </p>
                    ))}
                  </div>
                ) : data?.has_image ? (
                  <p className="text-xs text-slate-500">
                    VKIS: query là ảnh — xem trên DRES.
                  </p>
                ) : (
                  <p className="text-xs text-slate-500">Chưa có query cho task này.</p>
                )}
              </div>

              <div className="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (!queryText) return
                    onUseQuery(queryText)
                    setOpen(false)
                  }}
                  disabled={!queryText}
                  className={`h-9 rounded-lg px-3 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 ${
                    queryText
                      ? 'bg-blue-600 text-white hover:bg-blue-700'
                      : 'cursor-not-allowed bg-slate-200 text-slate-500'
                  }`}
                >
                  {sequential ? 'Dùng chuỗi' : 'Dùng query'}
                </button>
                <button
                  type="button"
                  onClick={() => void copy()}
                  disabled={!queryText}
                  className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 disabled:cursor-not-allowed disabled:text-slate-500"
                >
                  {copied ? 'Đã copy' : 'Copy'}
                </button>
                <span className="ml-auto text-[10px] text-slate-500">
                  {segments.length > 0 ? `${segments.length} đoạn` : ''}
                </span>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  )
}
