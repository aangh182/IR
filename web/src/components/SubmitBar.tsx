import { forwardRef, useEffect, useImperativeHandle, useState } from 'react'

import { formatMs, parseTimestamp } from '../format'
import type {
  DresStatus,
  DresSubmitKind,
  DresSubmitRequest,
  DresSubmitResult,
  FrameOption,
  Hit,
} from '../types'
import { Icon } from './Icon'

export type SubmitHandle = {
  submit: () => void
  copy: () => Promise<void>
}

type Props = {
  hit: Hit | null
  frame: FrameOption | null
}

const KINDS: { id: DresSubmitKind; label: string }[] = [
  { id: 'kis', label: 'KIS' },
  { id: 'qa', label: 'Q&A' },
  { id: 'trake', label: 'TRAKE' },
  { id: 'raw', label: 'Raw' },
]

const CATEGORY_STYLE: Record<string, string> = {
  correct: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  wrong: 'border-red-200 bg-red-50 text-red-900',
  review: 'border-amber-200 bg-amber-50 text-amber-900',
  unknown: 'border-slate-200 bg-slate-50 text-slate-800',
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

async function chooseEvaluation(evaluationId: string): Promise<void> {
  const response = await fetch('/api/dres/evaluation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ evaluation_id: evaluationId }),
  })
  if (!response.ok) {
    const body = (await response.json()) as { detail?: string }
    throw new Error(body.detail ?? `HTTP ${response.status}`)
  }
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

export const SubmitBar = forwardRef<SubmitHandle, Props>(function SubmitBar(
  { hit, frame },
  ref,
) {
  const [status, setStatus] = useState<DresStatus | null>(null)
  const [kindOverride, setKindOverride] = useState<DresSubmitKind | null>(null)
  const [videoOverride, setVideoOverride] = useState<string | null>(null)
  const [timeOverride, setTimeOverride] = useState<string | null>(null)
  const [answer, setAnswer] = useState('')
  const [framesInput, setFramesInput] = useState('')
  const [raw, setRaw] = useState('{\n  "answerSets": [\n    { "answers": [] }\n  ]\n}')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<DresSubmitResult | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [choosing, setChoosing] = useState(false)
  const [choiceError, setChoiceError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [payloadOpen, setPayloadOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let active = true
    const load = () => {
      fetchStatus()
        .then((body) => {
          if (active) setStatus(body)
        })
        .catch(() => {
          if (active) {
            setStatus({ configured: false, user: null, evaluation: null, task: null })
          }
        })
    }
    load()
    const timer = window.setInterval(load, 15000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [reloadKey])

  useEffect(() => {
    setVideoOverride(null)
    setTimeOverride(null)
    setResult(null)
    setSubmitError(null)
  }, [hit?.video_id, frame?.ts_ms])

  useEffect(() => {
    setAnswer('')
    setFramesInput('')
  }, [hit?.video_id])

  const task = status?.task ?? null
  const kind = kindOverride ?? kindForTask(task?.task_group)
  const videoId = videoOverride ?? hit?.video_id ?? ''
  const timeInput = timeOverride ?? (frame ? formatMs(frame.ts_ms) : '')
  const tsMs = parseTimestamp(timeInput)
  const answers = buildAnswers({
    kind,
    videoId,
    tsMs,
    answer,
    frames: framesInput,
    raw,
  })
  const invalid = typeof answers === 'string'
  const preview =
    kind === 'raw' && !invalid
      ? JSON.stringify(JSON.parse(raw), null, 2)
      : invalid
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
  const configured = status?.configured === true
  const needsChoice = status?.needs_choice === true
  const canSubmit =
    !invalid && !submitting && configured && !needsChoice && Boolean(hit)

  async function submit() {
    if (!canSubmit) return
    setSubmitting(true)
    setSubmitError(null)
    setResult(null)
    try {
      const evaluationId = status?.evaluation?.id ?? null
      const payload: DresSubmitRequest =
        kind === 'raw'
          ? { kind: 'raw', payload: JSON.parse(raw), evaluation_id: evaluationId }
          : kind === 'trake'
            ? {
                kind,
                video_id: videoId,
                frame_ids: framesInput
                  .split(',')
                  .map((part) => Number(part.trim()))
                  .filter((value) => Number.isFinite(value)),
                evaluation_id: evaluationId,
              }
            : kind === 'qa'
              ? { kind, video_id: videoId, ts_ms: tsMs, answer, evaluation_id: evaluationId }
              : { kind, video_id: videoId, ts_ms: tsMs, evaluation_id: evaluationId }

      const response = await fetch('/api/dres/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const body = (await response.json()) as DresSubmitResult
      if (!response.ok) throw new Error(body.detail ?? `HTTP ${response.status}`)
      setResult(body)
      setAdvancedOpen(false)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setSubmitting(false)
    }
  }

  async function copy() {
    if (invalid) {
      setSubmitError(answers as string)
      return
    }
    try {
      await navigator.clipboard.writeText(preview)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setSubmitError('Không copy được payload.')
    }
  }

  useImperativeHandle(ref, () => ({
    submit: () => {
      void submit()
    },
    copy,
  }))

  async function pickEvaluation(evaluationId: string) {
    if (!evaluationId || choosing) return
    setChoosing(true)
    setChoiceError(null)
    try {
      await chooseEvaluation(evaluationId)
      setReloadKey((value) => value + 1)
    } catch (err) {
      setChoiceError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setChoosing(false)
    }
  }

  return (
    <section
      aria-label="Nộp bài DRES"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 backdrop-blur"
    >
      {(result || submitError || choiceError) && (
        <div className="mx-auto w-full max-w-[1800px] px-3 pt-2 sm:px-5">
          {result && (
            <div
              role="status"
              className={`flex items-start gap-2 rounded-lg border px-3 py-2 ${CATEGORY_STYLE[result.category ?? 'unknown']}`}
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">
                  {CATEGORY_LABEL[result.category ?? 'unknown']}
                  {result.submission ? ` · ${result.submission}` : ''}
                </p>
                {result.description && (
                  <p className="mt-0.5 text-xs">{result.description}</p>
                )}
                <p className="mt-0.5 font-mono text-[10px] opacity-80">
                  HTTP {result.http_status ?? '—'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setResult(null)}
                aria-label="Đóng kết quả"
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md opacity-60 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current"
              >
                <Icon name="close" className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          {submitError && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-900"
            >
              <p className="min-w-0 flex-1 text-xs">{submitError}</p>
              <button
                type="button"
                onClick={() => setSubmitError(null)}
                aria-label="Đóng lỗi"
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md opacity-60 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
              >
                <Icon name="close" className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          {choiceError && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900">
              {choiceError}
            </div>
          )}
        </div>
      )}

      {advancedOpen && (
        <div className="mx-auto w-full max-w-[1800px] px-3 pb-2 sm:px-5">
          <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-medium text-slate-500">Loại bài</span>
              <div className="flex rounded-lg border border-slate-200 p-0.5">
                {KINDS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setKindOverride(item.id)}
                    aria-pressed={kind === item.id}
                    className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 ${
                      kind === item.id
                        ? 'bg-slate-900 text-white'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => {
                  setTimeOverride(null)
                  setVideoOverride(null)
                }}
                className="text-[11px] text-slate-500 transition-colors hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
              >
                Đặt lại theo frame
              </button>
              <button
                type="button"
                onClick={() => setPayloadOpen((value) => !value)}
                className="ml-auto text-[11px] text-slate-500 transition-colors hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
              >
                {payloadOpen ? 'Ẩn payload' : 'Xem payload'}
              </button>
            </div>

            {kind === 'raw' && (
              <textarea
                value={raw}
                onChange={(event) => setRaw(event.target.value)}
                spellCheck={false}
                rows={6}
                aria-label="Raw JSON payload"
                className="mt-2 w-full rounded-lg border border-slate-200 bg-slate-50 p-2 font-mono text-[11px] text-slate-800 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-600/15"
              />
            )}

            {payloadOpen && (
              <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-2 font-mono text-[10px] leading-relaxed text-slate-600">
                {preview}
              </pre>
            )}

            {status?.error && <p className="mt-2 text-[11px] text-red-700">{status.error}</p>}
            {needsChoice && (
              <p className="mt-2 text-[11px] text-amber-700">
                Có nhiều đề ACTIVE. Chọn đề trước khi nộp.
              </p>
            )}
          </div>
        </div>
      )}

      <div className="mx-auto flex w-full max-w-[1800px] flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2 sm:px-5">
        <div className="flex min-w-0 items-center gap-2">
          <span
            aria-hidden="true"
            className={`h-2 w-2 shrink-0 rounded-full ${
              status === null
                ? 'bg-slate-400'
                : configured
                  ? 'bg-blue-500'
                  : 'bg-amber-500'
            }`}
          />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <input
                value={videoId}
                onChange={(event) => setVideoOverride(event.target.value)}
                placeholder="video_id"
                aria-label="Video ID"
                spellCheck={false}
                className="w-32 rounded-md px-1.5 py-1 font-mono text-sm font-semibold text-slate-900 outline-none transition-colors placeholder:text-slate-500 hover:bg-slate-50 focus:bg-blue-50/60 focus:ring-2 focus:ring-blue-600/20"
              />
              <span className="text-slate-500">@</span>
              <input
                value={timeInput}
                onChange={(event) => setTimeOverride(event.target.value)}
                placeholder="00:00.000"
                aria-label="Thời gian"
                spellCheck={false}
                aria-invalid={Boolean(timeInput) && tsMs === null}
                className={`w-24 rounded-md px-1.5 py-1 font-mono text-sm tabular-nums outline-none transition-colors placeholder:text-slate-500 hover:bg-slate-50 focus:bg-blue-50/60 focus:ring-2 focus:ring-blue-600/20 ${
                  timeInput && tsMs === null ? 'text-red-600' : 'text-slate-600'
                }`}
              />
            </div>
            <p
              className={`truncate text-[10px] ${
                timeInput && tsMs === null ? 'text-red-600' : 'text-slate-500'
              }`}
            >
              {timeInput && tsMs === null
                ? 'Thời gian không hợp lệ'
                : `${status?.user ? status.user.username : 'DRES chưa cấu hình'}${
                    status?.evaluation ? ` · ${status.evaluation.name}` : ''
                  }${task ? ` · ${task.task_group}` : ''}`}
            </p>
          </div>
        </div>

        {kind === 'qa' && (
          <input
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            placeholder="Đáp án"
            aria-label="Câu trả lời"
            className="h-9 w-40 min-w-0 rounded-lg border border-slate-200 bg-white px-2.5 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-500 focus:border-blue-600 focus:ring-2 focus:ring-blue-600/15"
          />
        )}
        {kind === 'trake' && (
          <input
            value={framesInput}
            onChange={(event) => setFramesInput(event.target.value)}
            placeholder="Frame IDs"
            aria-label="Frame IDs"
            spellCheck={false}
            className="h-9 w-44 min-w-0 rounded-lg border border-slate-200 bg-white px-2.5 font-mono text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-500 focus:border-blue-600 focus:ring-2 focus:ring-blue-600/15"
          />
        )}

        <div className="ml-auto flex flex-wrap items-center gap-2">
          {(status?.evaluations?.length ?? 0) > 1 && (
            <select
              value={status?.evaluation?.id ?? ''}
              onChange={(event) => void pickEvaluation(event.target.value)}
              disabled={choosing}
              aria-label="Đề đang chạy"
              className="h-9 max-w-44 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700 outline-none transition-colors focus:border-blue-600 focus:ring-2 focus:ring-blue-600/15 disabled:bg-slate-100"
            >
              {!status?.evaluation && <option value="">Chọn đề</option>}
              {status?.evaluations?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} [{item.status}]
                </option>
              ))}
            </select>
          )}

          <button
            type="button"
            onClick={() => void copy()}
            aria-label={copied ? 'Đã copy payload' : 'Copy payload'}
            title={copied ? 'Đã copy' : 'Copy payload (C)'}
            className={`flex h-9 w-9 items-center justify-center rounded-lg border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 ${
              copied
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
            }`}
          >
            <Icon name={copied ? 'check' : 'copy'} className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={() => setAdvancedOpen((value) => !value)}
            aria-expanded={advancedOpen}
            aria-label="Tùy chọn nộp bài"
            title="Tùy chọn nộp bài"
            className={`flex h-9 w-9 items-center justify-center rounded-lg border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 ${
              advancedOpen
                ? 'border-slate-300 bg-slate-100 text-slate-900'
                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
            }`}
          >
            <Icon name="more" className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={() => void submit()}
            disabled={!canSubmit}
            className={`flex h-9 items-center gap-2 rounded-lg px-4 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 focus-visible:ring-offset-2 ${
              canSubmit
                ? 'bg-emerald-700 text-white hover:bg-emerald-600'
                : 'cursor-not-allowed bg-slate-200 text-slate-600'
            }`}
          >
            {submitting ? 'Đang nộp...' : 'Nộp bài'}
            {canSubmit && (
              <kbd className="hidden rounded border border-white/25 px-1 font-mono text-[10px] font-normal text-white/80 sm:inline">
                S
              </kbd>
            )}
          </button>
        </div>
      </div>
    </section>
  )
})
