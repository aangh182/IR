import { useEffect, useState } from 'react'

import { formatMs, parseTimestamp } from '../format'
import type {
  DresStatus,
  DresSubmitKind,
  DresSubmitRequest,
  DresSubmitResult,
  FrameOption,
  Hit,
} from '../types'

type Props = {
  hit: Hit | null
  frame: FrameOption | null
}

const TABS: { id: DresSubmitKind; label: string }[] = [
  { id: 'kis', label: 'KIS' },
  { id: 'qa', label: 'Q&A' },
  { id: 'trake', label: 'TRAKE' },
  { id: 'raw', label: 'Raw JSON' },
]

const CATEGORY_STYLE: Record<string, string> = {
  correct: 'border-emerald-300 bg-emerald-50 text-emerald-800',
  wrong: 'border-red-300 bg-red-50 text-red-800',
  review: 'border-amber-300 bg-amber-50 text-amber-800',
  unknown: 'border-slate-300 bg-slate-100 text-slate-700',
}

const CATEGORY_LABEL: Record<string, string> = {
  correct: 'CHÍNH XÁC',
  wrong: 'SAI',
  review: 'ĐANG THẨM ĐỊNH',
  unknown: 'KHÔNG RÕ',
}

function kindForTask(taskGroup: string | undefined): DresSubmitKind {
  const group = (taskGroup ?? '').toLowerCase()
  if (group === 'qa') return 'qa'
  if (group === 'trake') return 'trake'
  return 'kis'
}

async function fetchStatus(): Promise<DresStatus> {
  const response = await fetch('/api/dres/status')
  return (await response.json()) as DresStatus
}

function buildAnswers(input: {
  kind: DresSubmitKind
  videoId: string
  tsMs: number | null
  answer: string
  frames: string
  raw: string
}): unknown[] | string {
  const { kind, videoId, tsMs, answer, frames, raw } = input
  const video = videoId.trim()

  if (kind === 'raw') {
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      return 'JSON không hợp lệ'
    }
    const answerSets = (parsed as { answerSets?: unknown })?.answerSets
    if (!Array.isArray(answerSets) || answerSets.length === 0) {
      return 'Payload phải có answerSets không rỗng'
    }
    const answers = answerSets.flatMap((set) => {
      const items = (set as { answers?: unknown })?.answers
      return Array.isArray(items) ? items : []
    })
    return answers.length > 0 ? answers : 'Payload không có answer nào'
  }

  if (!video) return 'Thiếu Video ID'

  if (kind === 'trake') {
    const ids = frames
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean)
    if (ids.length === 0) return 'Thiếu frame ids'
    return [{ text: `TR-${video}-${ids.join(',')}` }]
  }

  if (tsMs === null) return 'Thiếu thời gian frame'

  if (kind === 'qa') {
    if (!answer.trim()) return 'Thiếu câu trả lời'
    return [{ text: `QA-${answer.trim()}-${video}-${tsMs}` }]
  }

  return [{ mediaItemName: video, start: tsMs, end: tsMs }]
}

export function DresPanel({ hit, frame }: Props) {
  const [status, setStatus] = useState<DresStatus | null>(null)
  const [kindOverride, setKindOverride] = useState<DresSubmitKind | null>(null)
  const [videoOverride, setVideoOverride] = useState<string | null>(null)
  const [timeOverride, setTimeOverride] = useState<string | null>(null)
  const [answer, setAnswer] = useState('')
  const [frames, setFrames] = useState('')
  const [raw, setRaw] = useState('{\n  "answerSets": [\n    { "answers": [] }\n  ]\n}')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<DresSubmitResult | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const load = () => {
      fetchStatus()
        .then((body) => {
          if (active) setStatus(body)
        })
        .catch(() => {
          if (active) setStatus({ configured: false, user: null, evaluation: null, task: null })
        })
    }
    load()
    const timer = window.setInterval(load, 15000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  const task = status?.task ?? null
  const kind = kindOverride ?? kindForTask(task?.task_group)
  const videoId = videoOverride ?? hit?.video_id ?? ''
  const timeInput = timeOverride ?? (frame ? formatMs(frame.ts_ms) : '')
  const tsMs = parseTimestamp(timeInput)

  const answers = buildAnswers({ kind, videoId, tsMs, answer, frames, raw })
  const invalid = typeof answers === 'string'

  const preview = invalid
    ? (answers as string)
    : JSON.stringify(
        {
          answerSets: [
            task ? { taskName: task.name, answers } : { answers },
          ],
        },
        null,
        2,
      )

  async function submit() {
    if (invalid || submitting || !status?.configured) return
    setSubmitting(true)
    setSubmitError(null)
    setResult(null)
    try {
      const payload: DresSubmitRequest =
        kind === 'raw'
          ? { kind: 'raw', payload: JSON.parse(raw) }
          : kind === 'trake'
            ? {
                kind,
                video_id: videoId,
                frame_ids: frames
                  .split(',')
                  .map((part) => Number(part.trim()))
                  .filter((value) => Number.isFinite(value)),
              }
            : kind === 'qa'
              ? { kind, video_id: videoId, ts_ms: tsMs, answer }
              : { kind, video_id: videoId, ts_ms: tsMs }

      const response = await fetch('/api/dres/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const body = (await response.json()) as DresSubmitResult
      if (!response.ok) throw new Error(body.detail ?? `HTTP ${response.status}`)
      setResult(body)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-[0.24em] text-slate-500">DRES</p>
          <p className="truncate text-sm font-semibold text-slate-900">
            {status?.user ? status.user.username : 'Chưa cấu hình'}
          </p>
        </div>
        <p className="shrink-0 text-right text-[10px] leading-relaxed text-slate-500">
          {status?.evaluation ? status.evaluation.name : '—'}
          <br />
          {status?.evaluation ? status.evaluation.status : ''}
        </p>
      </div>

      {status?.error && (
        <p className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-[11px] text-red-700">
          {status.error}
        </p>
      )}

      {task ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-[11px]">
          <div className="flex items-center justify-between">
            <span className="text-slate-500">Task</span>
            <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-sky-700">
              {task.task_group}
            </span>
          </div>
          <p className="mt-1 truncate font-mono text-slate-900">{task.name}</p>
          <p className="text-slate-500">{task.task_type}</p>
        </div>
      ) : (
        status?.configured && (
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-500">
            Không có task nào đang chạy.
          </p>
        )
      )}

      <div className="grid grid-cols-4 gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setKindOverride(tab.id)}
            aria-pressed={kind === tab.id}
            className={`rounded-md px-1.5 py-1.5 text-[11px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40 ${
              kind === tab.id
                ? 'bg-slate-900 text-white'
                : 'text-slate-600 hover:bg-white hover:text-slate-900'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {kind === 'raw' ? (
        <textarea
          value={raw}
          onChange={(event) => setRaw(event.target.value)}
          spellCheck={false}
          rows={8}
          className="w-full rounded-lg border border-slate-300 bg-white p-2 font-mono text-base text-slate-900 outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/15 sm:text-[11px]"
        />
      ) : (
        <div className="space-y-2">
          <label className="block text-[10px] uppercase tracking-[0.16em] text-slate-500">
            Video ID
            <input
              value={videoId}
              onChange={(event) => setVideoOverride(event.target.value)}
              placeholder="video_0108"
              spellCheck={false}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-base text-slate-900 outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/15 sm:text-sm"
            />
          </label>

          {kind === 'qa' && (
            <label className="block text-[10px] uppercase tracking-[0.16em] text-slate-500">
              Câu trả lời
              <input
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="42"
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/15 sm:text-sm"
              />
            </label>
          )}

          {kind === 'trake' ? (
            <label className="block text-[10px] uppercase tracking-[0.16em] text-slate-500">
              Frame IDs
              <input
                value={frames}
                onChange={(event) => setFrames(event.target.value)}
                placeholder="140, 395, 820, 1450"
                spellCheck={false}
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-base text-slate-900 outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/15 sm:text-sm"
              />
            </label>
          ) : (
            <label className="block text-[10px] uppercase tracking-[0.16em] text-slate-500">
              Thời gian frame
              <input
                value={timeInput}
                onChange={(event) => setTimeOverride(event.target.value)}
                placeholder="00:18.500"
                spellCheck={false}
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-base text-slate-900 outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/15 sm:text-sm"
              />
              <span className="mt-1 block font-mono text-[10px] normal-case tracking-normal text-slate-500">
                {tsMs === null ? 'MM:SS.mmm hoặc ms' : `${tsMs} ms`}
              </span>
            </label>
          )}
        </div>
      )}

      <details className="rounded-lg border border-slate-200 bg-slate-50">
        <summary className="cursor-pointer select-none px-3 py-2 text-[11px] text-slate-600">
          Payload gửi lên DRES
        </summary>
        <pre className="max-h-40 overflow-auto border-t border-slate-200 p-3 font-mono text-[10px] leading-relaxed text-slate-600">
          {preview}
        </pre>
      </details>

      <div className="sticky bottom-0 -mx-3 -mb-3 space-y-2 rounded-b-xl border-t border-slate-200 bg-white/95 px-3 pb-3 pt-3 backdrop-blur">
        <button
          type="button"
          onClick={() => void submit()}
          disabled={invalid || submitting || !status?.configured}
          className="w-full rounded-lg bg-emerald-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-emerald-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40 focus-visible:ring-offset-2 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
        >
          {submitting ? 'Đang nộp...' : 'Nộp bài (Submit)'}
        </button>

        {result && (
          <div
            className={`rounded-lg border px-3 py-2 ${CATEGORY_STYLE[result.category ?? 'unknown']}`}
          >
            <p className="text-sm font-semibold">
              {CATEGORY_LABEL[result.category ?? 'unknown']}
              {result.submission ? ` · ${result.submission}` : ''}
            </p>
            {result.description && <p className="mt-0.5 text-xs">{result.description}</p>}
            <p className="mt-0.5 font-mono text-[10px] opacity-80">
              HTTP {result.http_status ?? '—'}
            </p>
          </div>
        )}

        {submitError && (
          <p className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-[11px] text-red-700">
            {submitError}
          </p>
        )}
      </div>
    </section>
  )
}
