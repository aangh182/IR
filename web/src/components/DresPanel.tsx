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
  correct: 'border-emerald-500/40 bg-emerald-500/15 text-emerald-200',
  wrong: 'border-red-500/40 bg-red-500/15 text-red-200',
  review: 'border-amber-500/40 bg-amber-500/15 text-amber-200',
  unknown: 'border-slate-600 bg-slate-800 text-slate-300',
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
    <div className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">DRES</p>
          <p className="text-sm font-semibold text-slate-100">
            {status?.user ? status.user.username : 'Chưa cấu hình'}
          </p>
        </div>
        <p className="text-right text-[11px] text-slate-500">
          {status?.evaluation ? status.evaluation.name : '—'}
          <br />
          {status?.evaluation ? status.evaluation.status : ''}
        </p>
      </div>

      {status?.error && (
        <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {status.error}
        </p>
      )}

      {task ? (
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-slate-500">Task</span>
            <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-sky-300">
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

      <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-950/60 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setKindOverride(tab.id)}
            className={`flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition ${
              kind === tab.id ? 'bg-indigo-500 text-white' : 'text-slate-400 hover:text-slate-200'
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
          className="w-full rounded-lg border border-slate-700 bg-slate-950 p-2 font-mono text-[11px] text-slate-200 outline-none focus:border-indigo-400"
        />
      ) : (
        <div className="space-y-2">
          <label className="block text-xs text-slate-500">
            Video ID
            <input
              value={videoId}
              onChange={(event) => setVideoOverride(event.target.value)}
              placeholder="video_0108"
              spellCheck={false}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-indigo-400"
            />
          </label>

          {kind === 'qa' && (
            <label className="block text-xs text-slate-500">
              Câu trả lời
              <input
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="42"
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400"
              />
            </label>
          )}

          {kind === 'trake' ? (
            <label className="block text-xs text-slate-500">
              Frame IDs (cách nhau bởi dấu phẩy)
              <input
                value={frames}
                onChange={(event) => setFrames(event.target.value)}
                placeholder="140, 395, 820, 1450"
                spellCheck={false}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-indigo-400"
              />
            </label>
          ) : (
            <label className="block text-xs text-slate-500">
              Thời gian frame (MM:SS.mmm hoặc ms)
              <input
                value={timeInput}
                onChange={(event) => setTimeOverride(event.target.value)}
                placeholder="00:18.500"
                spellCheck={false}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-indigo-400"
              />
              <span className="mt-1 block font-mono text-[11px] text-slate-500">
                {tsMs === null ? '—' : `${tsMs} ms`}
              </span>
            </label>
          )}
        </div>
      )}

      <details className="rounded-lg border border-slate-800 bg-slate-950/80">
        <summary className="cursor-pointer select-none px-3 py-2 text-xs text-slate-400">
          Payload gửi lên DRES
        </summary>
        <pre className="max-h-40 overflow-auto border-t border-slate-800 p-3 font-mono text-[11px] leading-relaxed text-slate-400">
          {preview}
        </pre>
      </details>

      <div className="sticky bottom-0 -mx-4 -mb-4 space-y-2 rounded-b-2xl border-t border-slate-800 bg-slate-900/95 px-4 pb-4 pt-3 backdrop-blur">
        <button
          type="button"
          onClick={() => void submit()}
          disabled={invalid || submitting || !status?.configured}
          className="w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
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
            <p className="mt-0.5 font-mono text-[11px] opacity-80">
              HTTP {result.http_status ?? '—'}
            </p>
          </div>
        )}

        {submitError && (
          <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {submitError}
          </p>
        )}
      </div>
    </div>
  )
}
