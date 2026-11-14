import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { DresPanel } from './components/DresPanel'
import { ResultCard } from './components/ResultCard'
import { VideoPanel } from './components/VideoPanel'
import type {
  FrameOption,
  Health,
  Hit,
  ModelInfo,
  ObjectFacet,
  SearchResponse,
  Stats,
} from './types'

const EXAMPLES = [
  'a person speaking at a conference',
  'a football match in a stadium',
  'a news anchor at a desk',
]

async function responseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // fall through to HTTP status
  }
  return `HTTP ${response.status}`
}

function parseObjects(value: string): string[] {
  return [
    ...new Set(
      value
        .split(',')
        .map((part) => part.trim().toLowerCase())
        .filter(Boolean),
    ),
  ]
}

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)

  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(20)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [objectFilter, setObjectFilter] = useState('')
  const [objectOptions, setObjectOptions] = useState<ObjectFacet[]>([])
  const [results, setResults] = useState<Hit[]>([])
  const [selected, setSelected] = useState<Hit | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeFrame, setActiveFrame] = useState<FrameOption | null>(null)
  const handleActiveFrame = useCallback((frame: FrameOption) => setActiveFrame(frame), [])

  useEffect(() => {
    let cancelled = false

    Promise.all([
      fetch('/api/health').then((response) => {
        if (!response.ok) throw new Error(`health: HTTP ${response.status}`)
        return response.json() as Promise<Health>
      }),
      fetch('/api/stats').then((response) => {
        if (!response.ok) throw new Error(`stats: HTTP ${response.status}`)
        return response.json() as Promise<Stats>
      }),
      fetch('/api/objects').then((response) => {
        if (!response.ok) throw new Error(`objects: HTTP ${response.status}`)
        return response.json() as Promise<ObjectFacet[]>
      }),
      fetch('/api/models').then((response) => {
        if (!response.ok) throw new Error(`models: HTTP ${response.status}`)
        return response.json() as Promise<ModelInfo[]>
      }),
    ])
      .then(([healthData, statsData, objectData, modelData]) => {
        if (cancelled) return
        setHealth(healthData)
        setStats(statsData)
        setObjectOptions(objectData)
        setModels(modelData)
        const preferred =
          modelData.find((item) => item.default && item.available) ??
          modelData.find((item) => item.available) ??
          modelData.find((item) => item.default) ??
          modelData[0]
        if (preferred) setSelectedModel(preferred.name)
      })
      .catch((err: Error) => {
        if (!cancelled) setStatusError(err.message)
      })

    return () => {
      cancelled = true
    }
  }, [])

  async function runSearch(text: string) {
    const trimmed = text.trim()
    if (!trimmed || loading) return

    setLoading(true)
    setError(null)
    setHasSearched(true)

    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: trimmed,
          top_k: topK,
          objects: parseObjects(objectFilter),
          model: selectedModel || undefined,
        }),
      })
      if (!response.ok) throw new Error(await responseError(response))

      const data = (await response.json()) as SearchResponse
      setResults(data.results)
      setSelected(data.results[0] ?? null)
      setElapsed(data.elapsed_ms)
    } catch (err) {
      setResults([])
      setSelected(null)
      setElapsed(null)
      setError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setLoading(false)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void runSearch(query)
  }

  function toggleObject(label: string) {
    const current = parseObjects(objectFilter)
    const next = current.includes(label)
      ? current.filter((item) => item !== label)
      : [...current, label]
    setObjectFilter(next.join(', '))
  }

  const online = health?.status === 'ok'
  const indexReady = health?.index_ready === true
  const selectedModelInfo = models.find((item) => item.name === selectedModel) ?? null

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-5">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500">AIC2024</p>
            <h1 className="text-2xl font-semibold">Known-Item Search</h1>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {indexReady ? (
              <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300">
                {health?.index_count?.toLocaleString('vi-VN') ?? '?'} keyframes đã embed
              </span>
            ) : (
              <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-300">
                Index chưa sẵn sàng
              </span>
            )}
            <span className="flex items-center gap-2 text-xs text-slate-400">
              <span
                className={`h-2 w-2 rounded-full ${
                  online ? 'bg-emerald-400' : statusError ? 'bg-red-400' : 'bg-slate-500'
                }`}
              />
              {statusError ? 'API offline' : online ? `API ${health?.version}` : 'Đang kiểm tra...'}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
          <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Mô tả sự kiện bằng tiếng Anh..."
              spellCheck={false}
              className="flex-1 rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-indigo-400"
            />
            <label className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-950 px-3 text-xs text-slate-400">
              <span className="whitespace-nowrap">Model</span>
              <select
                value={selectedModel}
                onChange={(event) => setSelectedModel(event.target.value)}
                className="max-w-[190px] bg-transparent py-3 text-sm text-slate-100 outline-none"
              >
                {models.length === 0 && <option value="">(default)</option>}
                {models.map((item) => (
                  <option
                    key={item.name}
                    value={item.name}
                    disabled={!item.available}
                    className="bg-slate-900 text-slate-100"
                  >
                    {item.name} · {item.dim}d{item.available ? '' : ' · chưa có index'}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-950 px-3 text-xs text-slate-400">
              <span className="whitespace-nowrap">Top K</span>
              <input
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(event) => {
                  const next = Number(event.target.value)
                  setTopK(Number.isNaN(next) ? 1 : Math.min(50, Math.max(1, next)))
                }}
                className="w-14 bg-transparent py-3 text-center font-mono text-sm text-slate-100 outline-none"
              />
            </label>
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="rounded-xl bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            >
              {loading ? 'Đang tìm...' : 'Tìm'}
            </button>
          </form>

          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span>Ví dụ:</span>
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setQuery(example)
                  void runSearch(example)
                }}
                className="rounded-full border border-slate-700 px-3 py-1 text-slate-400 transition hover:border-slate-500 hover:text-slate-200"
              >
                {example}
              </button>
            ))}
          </div>

          <div className="mt-3 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={objectFilter}
                onChange={(event) => setObjectFilter(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    void runSearch(query)
                  }
                }}
                placeholder="Lọc object COCO: person, car, dog..."
                spellCheck={false}
                list="object-labels"
                className="flex-1 rounded-xl border border-slate-700 bg-slate-950 px-4 py-2 text-xs text-slate-200 outline-none placeholder:text-slate-600 focus:border-indigo-400"
              />
              <datalist id="object-labels">
                {objectOptions.map((option) => (
                  <option key={option.label} value={option.label} />
                ))}
              </datalist>
              {objectFilter && (
                <button
                  type="button"
                  onClick={() => setObjectFilter('')}
                  className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-400 transition hover:border-slate-500 hover:text-slate-200"
                >
                  Xoá lọc
                </button>
              )}
            </div>
            {objectOptions.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                <span>Object có sẵn:</span>
                {objectOptions.slice(0, 12).map((option) => {
                  const active = parseObjects(objectFilter).includes(option.label)
                  return (
                    <button
                      key={option.label}
                      type="button"
                      onClick={() => toggleObject(option.label)}
                      className={`rounded-full border px-2 py-0.5 transition ${
                        active
                          ? 'border-indigo-400 bg-indigo-500/20 text-indigo-200'
                          : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                      }`}
                    >
                      {option.label}{' '}
                      <span className="font-mono text-[10px] text-slate-500">
                        {option.keyframes.toLocaleString('vi-VN')}
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          {stats && (
            <p className="mt-3 text-xs text-slate-500">
              {stats.videos.toLocaleString('vi-VN')} video · {stats.shots.toLocaleString('vi-VN')} shot ·{' '}
              {stats.keyframes.toLocaleString('vi-VN')} keyframe ·{' '}
              {stats.follow_frames.toLocaleString('vi-VN')} frame lướt
            </p>
          )}

          {selectedModelInfo && (
            <p className="mt-1 text-xs text-slate-600">
              embedding: {selectedModelInfo.name} · {selectedModelInfo.model} ·{' '}
              {selectedModelInfo.keyframes !== null
                ? `${selectedModelInfo.keyframes.toLocaleString('vi-VN')} keyframes`
                : 'chưa có index'}
            </p>
          )}
        </section>

        {health && !indexReady && (
          <p className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
            Chưa thấy embedding artifacts. Chạy notebook Kaggle rồi `uv run ir import-shards &lt;zip&gt;` để bật search.
          </p>
        )}

        {statusError && (
          <p className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            Không kết nối được API: {statusError}
          </p>
        )}

        {error && (
          <p className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </p>
        )}

        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
          <section>
            <div className="mb-3 flex items-center justify-between text-sm text-slate-400">
              <span>{hasSearched ? `${results.length} kết quả` : 'Kết quả'}</span>
              {hasSearched && elapsed !== null && <span>{elapsed} ms</span>}
            </div>

            {results.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {results.map((hit) => (
                  <ResultCard
                    key={`${hit.video_id}-${hit.shot_idx}`}
                    hit={hit}
                    selected={selected?.video_id === hit.video_id && selected.shot_idx === hit.shot_idx}
                    onSelect={setSelected}
                  />
                ))}
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-800 p-10 text-center text-sm text-slate-500">
                {loading
                  ? 'Đang tìm...'
                  : hasSearched
                    ? 'Không có kết quả.'
                    : 'Nhập mô tả tiếng Anh để tìm keyframe.'}
              </div>
            )}
          </section>

          <aside className="lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto lg:pr-1">
            {selected ? (
              <div className="space-y-4">
                <DresPanel hit={selected} frame={activeFrame} />
                <VideoPanel
                  key={`${selected.video_id}-${selected.shot_idx}-${selected.start_ms}`}
                  hit={selected}
                  onActiveFrameChange={handleActiveFrame}
                />
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-800 p-10 text-center text-sm text-slate-500">
                Chọn một kết quả để xem frame và video.
              </div>
            )}
          </aside>
        </div>
      </main>
    </div>
  )
}

export default App
