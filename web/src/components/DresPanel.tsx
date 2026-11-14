import { useCallback, useEffect, useState } from 'react'

import { formatMs } from '../format'
import type { DresStatus, DresSubmitResult, FrameOption, Hit } from '../types'

type Props = {
  hit: Hit | null
  frame: FrameOption | null
}

export function DresPanel({ hit, frame }: Props) {
  const [status, setStatus] = useState<DresStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<DresSubmitResult | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/api/dres/status')
      const body = (await response.json()) as DresStatus
      setStatus(body)
      setStatusError(body.error ?? null)
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : 'Lỗi không xác định')
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 15000)
    return () => window.clearInterval(timer)
  }, [refresh])

  async function submit() {
    if (!hit || !frame || submitting) return
    setSubmitting(true)
    setSubmitError(null)
    setResult(null)
    try {
      const response = await fetch('/api/dres/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_id: hit.video_id,
          start_ms: frame.start_ms,
          end_ms: frame.end_ms,
        }),
      })
      const body = (await response.json()) as DresSubmitResult & { detail?: string }
      if (!response.ok) throw new Error(body.detail ?? `HTTP ${response.status}`)
      setResult(body)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setSubmitting(false)
    }
  }

  const task = status?.task ?? null

  return (
    <div className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">DRES</p>
          <p className="text-sm font-semibold text-slate-100">
            {status?.user ? status.user.username : 'Chưa cấu hình'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 transition hover:border-slate-500"
        >
          Làm mới
        </button>
      </div>

      {statusError && (
        <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {statusError}
        </p>
      )}

      {status?.evaluation && (
        <dl className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
            <dt className="text-slate-500">Evaluation</dt>
            <dd className="mt-1 truncate text-slate-200">{status.evaluation.name}</dd>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
            <dt className="text-slate-500">Trạng thái</dt>
            <dd className="mt-1 text-slate-200">{status.evaluation.status}</dd>
          </div>
        </dl>
      )}

      {task ? (
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-slate-500">Task</span>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                task.is_visual
                  ? 'bg-fuchsia-500/20 text-fuchsia-300'
                  : 'bg-sky-500/20 text-sky-300'
              }`}
            >
              {task.task_group}
            </span>
          </div>
          <p className="mt-1 font-mono text-slate-200">{task.name}</p>
          <p className="text-slate-500">{task.task_type}</p>
        </div>
      ) : (
        status?.configured && (
          <p className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-500">
            Không có task nào đang chạy.
          </p>
        )
      )}

      <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-xs">
        <p className="text-slate-500">Đáp án sẽ nộp</p>
        {hit && frame ? (
          <>
            <p className="mt-1 font-mono text-slate-200">{hit.video_id}</p>
            <p className="font-mono text-slate-400">
              {formatMs(frame.start_ms)} → {formatMs(frame.end_ms)}
            </p>
          </>
        ) : (
          <p className="mt-1 text-slate-600">Chọn một kết quả và frame trước.</p>
        )}
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!hit || !frame || submitting || !status?.configured}
        className="w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
      >
        {submitting ? 'Đang nộp...' : 'Nộp lên DRES'}
      </button>

      {result && (
        <p
          className={`rounded-lg border px-3 py-2 text-xs ${
            result.status
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
              : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
          }`}
        >
          {result.description || (result.status ? 'Đã nộp' : 'Bị từ chối')}
          {result.submission ? ` · ${result.submission}` : ''}
        </p>
      )}

      {submitError && (
        <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {submitError}
        </p>
      )}
    </div>
  )
}
