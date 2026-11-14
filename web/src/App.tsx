import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { DresPanel } from './components/DresPanel'
import { ResultCard } from './components/ResultCard'
import { VideoPanel } from './components/VideoPanel'
import { formatMs } from './format'
import type {
  FrameOption,
  Health,
  Hit,
  ModelInfo,
  ObjectFacet,
  SearchResponse,
  Stats,
} from './types'

const TOP_K_OPTIONS = [20, 30, 40, 50]

async function responseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // fall through to HTTP status
  }
  return `HTTP ${response.status}`
}

type ResultsSnapshot = {
  results: Hit[]
  elapsed: number | null
  lastQuery: string
  translatedQuery: string
  source: Hit
  filters: {
    includeBoilerplate: boolean
    dedup: boolean
    objectFilter: string
    topK: number
    selectedModel: string
  }
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
  const queryRef = useRef<HTMLTextAreaElement | null>(null)
  const [topK, setTopK] = useState(20)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [objectFilter, setObjectFilter] = useState('')
  const [objectOptions, setObjectOptions] = useState<ObjectFacet[]>([])
  const [includeBoilerplate, setIncludeBoilerplate] = useState(false)
  const [dedup, setDedup] = useState(true)
  const [results, setResults] = useState<Hit[]>([])
  const [selected, setSelected] = useState<Hit | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeFrame, setActiveFrame] = useState<FrameOption | null>(null)
  const [lastQuery, setLastQuery] = useState('')
  const [translatedQuery, setTranslatedQuery] = useState('')
  const [similarSource, setSimilarSource] = useState<Hit | null>(null)
  const [timelineSource, setTimelineSource] = useState<Hit | null>(null)
  const [previousResults, setPreviousResults] = useState<ResultsSnapshot | null>(null)
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

  useEffect(() => {
    if (!timelineSource?.kf_uid) return
    const target = document.querySelector(
      `[data-kf-uid="${timelineSource.kf_uid}"]`,
    )
    target?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [timelineSource, results])

  useEffect(() => {
    const element = queryRef.current
    if (!element) return
    const resize = () => {
      element.style.height = 'auto'
      element.style.height = `${element.scrollHeight + 2}px`
    }
    resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [query])

  async function runSearch(
    text: string,
    options?: { includeBoilerplate?: boolean; dedup?: boolean },
  ) {
    const trimmed = text.trim()
    if (!trimmed || loading) return

    const showBoilerplate = options?.includeBoilerplate ?? includeBoilerplate
    const useDedup = options?.dedup ?? dedup
    setLoading(true)
    setError(null)
    setHasSearched(true)
    setSimilarSource(null)
    setTimelineSource(null)
    setPreviousResults(null)
    setLastQuery(trimmed)
    setTranslatedQuery('')

    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: trimmed,
          top_k: topK,
          objects: parseObjects(objectFilter),
          model: selectedModel || undefined,
          include_boilerplate: showBoilerplate,
          dedup: useDedup,
        }),
      })
      if (!response.ok) throw new Error(await responseError(response))

      const data = (await response.json()) as SearchResponse
      setResults(data.results)
      setSelected(data.results[0] ?? null)
      setActiveFrame(null)
      setTranslatedQuery(data.translated_query ?? '')
      setElapsed(data.elapsed_ms)
    } catch (err) {
      setResults([])
      setSelected(null)
      setActiveFrame(null)
      setElapsed(null)
      setError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setLoading(false)
    }
  }

  async function runSimilar(
    hit: Hit,
    options?: { includeBoilerplate?: boolean; dedup?: boolean },
  ) {
    if (loading) return
    if (!hit.kf_uid) {
      setError('Frame này không có kf_uid trong index.')
      return
    }

    const showBoilerplate = options?.includeBoilerplate ?? includeBoilerplate
    const useDedup = options?.dedup ?? dedup
    if (!similarSource && !timelineSource) {
      setPreviousResults({
        results,
        elapsed,
        lastQuery,
        translatedQuery,
        source: hit,
        filters: {
          includeBoilerplate,
          dedup,
          objectFilter,
          topK,
          selectedModel,
        },
      })
    }
    setLoading(true)
    setError(null)
    setHasSearched(true)
    setTimelineSource(null)
    setSimilarSource(hit)
    setLastQuery('')
    setTranslatedQuery('')

    try {
      const response = await fetch('/api/similar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kf_uid: hit.kf_uid,
          top_k: topK,
          objects: parseObjects(objectFilter),
          model: selectedModel || undefined,
          include_boilerplate: showBoilerplate,
          dedup: useDedup,
        }),
      })
      if (!response.ok) throw new Error(await responseError(response))

      const data = (await response.json()) as SearchResponse
      setResults(data.results)
      setSelected(data.results[0] ?? null)
      setActiveFrame(null)
      setElapsed(data.elapsed_ms)
    } catch (err) {
      setResults([])
      setSelected(null)
      setActiveFrame(null)
      setElapsed(null)
      setError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setLoading(false)
    }
  }

  async function runTimeline(hit: Hit) {
    if (loading) return
    if (!hit.kf_uid) {
      setError('Frame này không có kf_uid trong index.')
      return
    }

    if (!similarSource && !timelineSource) {
      setPreviousResults({
        results,
        elapsed,
        lastQuery,
        translatedQuery,
        source: hit,
        filters: {
          includeBoilerplate,
          dedup,
          objectFilter,
          topK,
          selectedModel,
        },
      })
    }
    setLoading(true)
    setError(null)
    setHasSearched(true)
    setSimilarSource(null)
    setTimelineSource(hit)
    setLastQuery('')
    setTranslatedQuery('')

    try {
      const response = await fetch('/api/timeline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kf_uid: hit.kf_uid }),
      })
      if (!response.ok) throw new Error(await responseError(response))

      const data = (await response.json()) as SearchResponse
      setResults(data.results)
      setSelected(
        data.results.find((item) => item.kf_uid === hit.kf_uid) ??
          data.results[0] ??
          null,
      )
      setActiveFrame(null)
      setElapsed(data.elapsed_ms)
    } catch (err) {
      setResults([])
      setSelected(null)
      setActiveFrame(null)
      setElapsed(null)
      setError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setLoading(false)
    }
  }

  function submitSearch() {
    if (!query.trim()) {
      setError('Nhập mô tả sự kiện trước khi tìm.')
      return
    }
    void runSearch(query)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submitSearch()
  }

  const handleSelect = useCallback((hit: Hit) => {
    setSelected(hit)
    setActiveFrame(null)
  }, [])

  function handleSimilar(hit: Hit) {
    void runSimilar(hit)
  }

  function handleTimeline(hit: Hit) {
    void runTimeline(hit)
  }

  function backToResults() {
    if (loading) return
    const snapshot = previousResults
    setSimilarSource(null)
    setTimelineSource(null)
    setPreviousResults(null)
    setError(null)
    if (!snapshot) return
    setHasSearched(true)
    setResults(snapshot.results)
    setSelected(snapshot.source)
    setElapsed(snapshot.elapsed)
    setLastQuery(snapshot.lastQuery)
    setTranslatedQuery(snapshot.translatedQuery)
    setIncludeBoilerplate(snapshot.filters.includeBoilerplate)
    setDedup(snapshot.filters.dedup)
    setObjectFilter(snapshot.filters.objectFilter)
    setTopK(snapshot.filters.topK)
    setSelectedModel(snapshot.filters.selectedModel)
    setActiveFrame(null)
  }

  function toggleObject(label: string) {
    const current = parseObjects(objectFilter)
    const next = current.includes(label)
      ? current.filter((item) => item !== label)
      : [...current, label]
    setObjectFilter(next.join(', '))
  }

  function resetFilters() {
    setObjectFilter('')
    setIncludeBoilerplate(false)
    setDedup(true)
    setTopK(20)
    setError(null)
  }

  const online = health?.status === 'ok'
  const indexReady = health?.index_ready === true
  const selectedModelInfo = models.find((item) => item.name === selectedModel) ?? null
  const activeObjects = parseObjects(objectFilter)

  function keyframeTime(hit: Hit): number {
    return hit.frames.find((frame) => frame.is_keyframe)?.ts_ms ?? hit.start_ms
  }

  function isHitSelected(hit: Hit): boolean {
    if (!selected) return false
    if (selected.kf_uid !== null && hit.kf_uid !== null) {
      return selected.kf_uid === hit.kf_uid
    }
    return selected.video_id === hit.video_id && selected.shot_idx === hit.shot_idx
  }

  return (
    <div className="min-h-dvh bg-[#f5f3ee] text-slate-900 xl:h-dvh xl:overflow-hidden">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-[#fbfaf7]/95 backdrop-blur xl:static">
        <div className="flex h-14 items-center justify-between gap-3 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-slate-900 font-mono text-xs font-bold text-white">
              K
            </div>
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-[0.24em] text-slate-500">AIC2024</p>
              <h1 className="truncate text-sm font-semibold tracking-tight text-slate-900">
                Known-Item Search <span className="font-normal text-slate-400">/ console</span>
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-2 text-[11px]">
            <span
              className={`hidden items-center gap-1.5 rounded border px-2 py-1 sm:flex ${
                indexReady
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
                  : 'border-amber-300 bg-amber-50 text-amber-700'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  indexReady ? 'bg-emerald-500' : 'bg-amber-500'
                }`}
              />
              {indexReady
                ? `${(
                    selectedModelInfo?.keyframes ??
                    health?.index_count ??
                    0
                  ).toLocaleString('vi-VN')} keyframes`
                : 'Index chưa sẵn sàng'}
            </span>
            <span className="flex items-center gap-1.5 rounded border border-slate-200 bg-white px-2 py-1 text-slate-600">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  online ? 'bg-emerald-500' : statusError ? 'bg-red-500' : 'bg-slate-400'
                }`}
              />
              <span className="hidden sm:inline">
                {statusError ? 'API offline' : online ? `API ${health?.version}` : 'Đang kiểm tra...'}
              </span>
            </span>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 xl:h-[calc(100dvh-3.5rem)] xl:grid-cols-[300px_minmax(0,1fr)_400px] 2xl:grid-cols-[320px_minmax(0,1fr)_440px]">
        <aside
          aria-label="Tìm kiếm và bộ lọc"
          className="scroll-slim border-b border-slate-200 bg-[#fbfaf7] xl:min-h-0 xl:overflow-y-auto xl:border-b-0 xl:border-r"
        >
          <form
            onSubmit={handleSubmit}
            autoComplete="off"
            className="flex min-h-full flex-col gap-5 p-4 sm:p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Search</p>
                <h2 className="mt-1 text-sm font-semibold tracking-tight text-slate-900">
                  Tìm keyframe
                </h2>
              </div>
              <span className="rounded border border-slate-200 bg-white px-2 py-1 font-mono text-[10px] text-slate-500">
                {loading ? 'searching' : elapsed !== null ? `${elapsed} ms` : 'idle'}
              </span>
            </div>

            <div className="space-y-2">
              <label
                htmlFor="query"
                className="block text-[10px] uppercase tracking-[0.18em] text-slate-500"
              >
                Mô tả sự kiện
              </label>
              <textarea
                id="query"
                ref={queryRef}
                value={query}
                rows={1}
                onChange={(event) => {
                  setQuery(event.target.value)
                  if (error) setError(null)
                }}
                onKeyDown={(event) => {
                  if (
                    event.key === 'Enter' &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault()
                    submitSearch()
                  }
                }}
                placeholder="a person speaking at a conference"
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="off"
                spellCheck={false}
                enterKeyHint="search"
                className="block max-h-40 min-h-[46px] w-full resize-none overflow-y-auto rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-base leading-relaxed text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-amber-500 focus:ring-2 focus:ring-amber-500/15 sm:text-sm"
              />
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 rounded-lg bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900/40 focus-visible:ring-offset-2 focus-visible:ring-offset-[#fbfaf7] disabled:cursor-wait disabled:bg-slate-400"
                >
                  {loading ? 'Đang tìm...' : 'Tìm kiếm'}
                </button>
                <select
                  id="top-k"
                  aria-label="Top K"
                  value={topK}
                  onChange={(event) => setTopK(Number(event.target.value))}
                  className="w-24 rounded-lg border border-slate-300 bg-white px-2 py-3 text-sm font-medium text-slate-700 outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/15"
                >
                  {TOP_K_OPTIONS.map((value) => (
                    <option key={value} value={value}>
                      Top {value}
                    </option>
                  ))}
                </select>
              </div>
              {error && (
                <p
                  role="alert"
                  className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-[11px] leading-relaxed text-red-700"
                >
                  {error}
                </p>
              )}
            </div>

            <div className="border-t border-slate-200 pt-4">
              <div className="flex items-center justify-between">
                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Bộ lọc</p>
                {(objectFilter || includeBoilerplate || !dedup || topK !== 20) && (
                  <button
                    type="button"
                    onClick={resetFilters}
                    className="text-[11px] text-slate-500 transition hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40"
                  >
                    Đặt lại
                  </button>
                )}
              </div>

              <div className="mt-3 space-y-3">
                <label htmlFor="model" className="block">
                  <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                    Embedding
                  </span>
                  <select
                    id="model"
                    value={selectedModel}
                    onChange={(event) => setSelectedModel(event.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 outline-none transition focus:border-amber-500 focus:ring-2 focus:ring-amber-500/15 sm:text-sm"
                  >
                    {models.length === 0 && <option value="">(default)</option>}
                    {models.map((item) => (
                      <option key={item.name} value={item.name} disabled={!item.available}>
                        {item.name} · {item.dim}d
                        {item.available ? '' : ' · chưa có index'}
                      </option>
                    ))}
                  </select>
                </label>

                <label htmlFor="object-filter" className="block">
                  <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                    Object (COCO)
                  </span>
                  <input
                    id="object-filter"
                    value={objectFilter}
                    onChange={(event) => setObjectFilter(event.target.value)}
                    placeholder="person, car, dog..."
                    autoComplete="off"
                    spellCheck={false}
                    list="object-labels"
                    className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-amber-500 focus:ring-2 focus:ring-amber-500/15 sm:text-sm"
                  />
                  <datalist id="object-labels">
                    {objectOptions.map((option) => (
                      <option key={option.label} value={option.label} />
                    ))}
                  </datalist>
                </label>

                {objectOptions.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {objectOptions.slice(0, 12).map((option) => {
                      const active = activeObjects.includes(option.label)
                      return (
                        <button
                          key={option.label}
                          type="button"
                          onClick={() => toggleObject(option.label)}
                          aria-pressed={active}
                          className={`rounded-full border px-2 py-1 text-[10px] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40 ${
                            active
                              ? 'border-amber-500 bg-amber-50 text-amber-800'
                              : 'border-slate-300 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900'
                          }`}
                        >
                          {option.label}{' '}
                          <span className="font-mono text-[9px] opacity-60">
                            {option.keyframes.toLocaleString('vi-VN')}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                )}

                <div className="grid gap-2">
                  <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <span className="text-xs text-slate-700">Hiện boilerplate</span>
                    <input
                      type="checkbox"
                      checked={includeBoilerplate}
                      onChange={(event) => {
                        const next = event.target.checked
                        setIncludeBoilerplate(next)
                        if (hasSearched) {
                          if (similarSource) {
                            void runSimilar(similarSource, { includeBoilerplate: next })
                          } else if (timelineSource) {
                            void runTimeline(timelineSource)
                          } else if (query.trim()) {
                            void runSearch(query, { includeBoilerplate: next })
                          }
                        }
                      }}
                      className="h-4 w-4 accent-amber-500"
                    />
                  </label>
                  <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <span className="text-xs text-slate-700">Dedup ảnh trùng</span>
                    <input
                      type="checkbox"
                      checked={dedup}
                      onChange={(event) => {
                        const next = event.target.checked
                        setDedup(next)
                        if (hasSearched) {
                          if (similarSource) {
                            void runSimilar(similarSource, { dedup: next })
                          } else if (timelineSource) {
                            void runTimeline(timelineSource)
                          } else if (query.trim()) {
                            void runSearch(query, { dedup: next })
                          }
                        }
                      }}
                      className="h-4 w-4 accent-amber-500"
                    />
                  </label>
                </div>
              </div>
            </div>

            <div className="mt-auto space-y-3 border-t border-slate-200 pt-4">
              {health && !indexReady && (
                <p className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-800">
                  Chưa thấy embedding artifacts. Chạy notebook Kaggle rồi{' '}
                  <code className="font-mono">uv run ir import-shards &lt;zip&gt;</code>.
                </p>
              )}
              {statusError && (
                <p className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-[11px] leading-relaxed text-red-700">
                  Không kết nối được API: {statusError}
                </p>
              )}

              <div>
                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Corpus</p>
                <dl className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
                  <div className="rounded border border-slate-200 bg-white px-2 py-1.5">
                    <dt className="text-slate-500">Videos</dt>
                    <dd className="font-mono text-slate-900">
                      {stats?.videos.toLocaleString('vi-VN') ?? '—'}
                    </dd>
                  </div>
                  <div className="rounded border border-slate-200 bg-white px-2 py-1.5">
                    <dt className="text-slate-500">Keyframes</dt>
                    <dd className="font-mono text-slate-900">
                      {stats?.keyframes.toLocaleString('vi-VN') ?? '—'}
                    </dd>
                  </div>
                  <div className="rounded border border-slate-200 bg-white px-2 py-1.5">
                    <dt className="text-slate-500">Shots</dt>
                    <dd className="font-mono text-slate-900">
                      {stats?.shots.toLocaleString('vi-VN') ?? '—'}
                    </dd>
                  </div>
                  <div className="rounded border border-slate-200 bg-white px-2 py-1.5">
                    <dt className="text-slate-500">Follow</dt>
                    <dd className="font-mono text-slate-900">
                      {stats?.follow_frames.toLocaleString('vi-VN') ?? '—'}
                    </dd>
                  </div>
                </dl>
              </div>

              {selectedModelInfo && (
                <p className="font-mono text-[10px] leading-relaxed text-slate-500">
                  {selectedModelInfo.name} · {selectedModelInfo.dim}d ·{' '}
                  {selectedModelInfo.keyframes !== null
                    ? `${selectedModelInfo.keyframes.toLocaleString('vi-VN')} kf`
                    : 'chưa có index'}
                  {selectedModelInfo.boilerplate !== null &&
                    ` · ${selectedModelInfo.boilerplate.toLocaleString('vi-VN')} boiler`}
                </p>
              )}
            </div>
          </form>
        </aside>

        <main
          aria-label="Kết quả tìm kiếm"
          className="panel-grid scroll-slim min-h-0 xl:overflow-y-auto"
        >
          <div className="space-y-4 p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Results</p>
                <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">
                  {loading
                    ? 'Đang tìm...'
                    : hasSearched
                      ? `${results.length} ${
                          similarSource
                            ? 'frame tương tự'
                            : timelineSource
                              ? 'keyframe lân cận'
                              : 'keyframe'
                        }`
                      : 'Chưa có truy vấn'}
                </h2>
                {hasSearched && lastQuery && (
                  <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-600">
                    {translatedQuery && translatedQuery !== lastQuery ? (
                      <>
                        <span className="text-slate-500">{lastQuery}</span>
                        <span className="mx-1.5 text-slate-400">→</span>
                        <span>{translatedQuery}</span>
                      </>
                    ) : (
                      lastQuery
                    )}
                  </p>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-1.5 font-mono text-[10px] text-slate-600">
                {timelineSource ? (
                  <span className="rounded border border-sky-300 bg-sky-50 px-2 py-1 text-sky-700">
                    timeline
                  </span>
                ) : (
                  <>
                    <span className="rounded border border-slate-300 bg-white px-2 py-1">
                      {selectedModel || 'default'}
                    </span>
                    <span className="rounded border border-slate-300 bg-white px-2 py-1">
                      {dedup ? 'dedup' : 'no-dedup'}
                    </span>
                  </>
                )}
                {elapsed !== null && (
                  <span className="rounded border border-slate-300 bg-white px-2 py-1">
                    {elapsed} ms
                  </span>
                )}
              </div>
            </div>

            {similarSource && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2">
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <img
                    src={similarSource.keyframe_url}
                    alt=""
                    className="h-10 w-16 shrink-0 rounded border border-amber-200 object-cover"
                  />
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-[0.18em] text-amber-700">
                      Similar search
                    </p>
                    <p className="truncate text-xs text-amber-900">
                      Tương tự{' '}
                      <span className="font-mono">{similarSource.video_id}</span> ·{' '}
                      {formatMs(keyframeTime(similarSource))}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => void runSimilar(similarSource)}
                    disabled={loading}
                    className="rounded-md border border-amber-300 bg-white px-2.5 py-1.5 text-xs font-medium text-amber-800 transition hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Chạy lại
                  </button>
                  <button
                    type="button"
                    onClick={backToResults}
                    disabled={loading}
                    className="rounded-md bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900/40 focus-visible:ring-offset-2 focus-visible:ring-offset-amber-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    ← Quay lại
                  </button>
                </div>
              </div>
            )}

            {timelineSource && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sky-300 bg-sky-50 px-3 py-2">
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <img
                    src={timelineSource.keyframe_url}
                    alt=""
                    className="h-10 w-16 shrink-0 rounded border border-sky-200 object-cover"
                  />
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-[0.18em] text-sky-700">
                      Timeline
                    </p>
                    <p className="truncate text-xs text-sky-900">
                      Keyframe lân cận ·{' '}
                      <span className="font-mono">{timelineSource.video_id}</span> ·{' '}
                      {formatMs(keyframeTime(timelineSource))}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => void runTimeline(timelineSource)}
                    disabled={loading}
                    className="rounded-md border border-sky-300 bg-white px-2.5 py-1.5 text-xs font-medium text-sky-800 transition hover:bg-sky-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/40 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Chạy lại
                  </button>
                  <button
                    type="button"
                    onClick={backToResults}
                    disabled={loading}
                    className="rounded-md bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900/40 focus-visible:ring-offset-2 focus-visible:ring-offset-sky-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    ← Quay lại
                  </button>
                </div>
              </div>
            )}

            {loading ? (
              <div className="result-grid" aria-busy="true">
                {Array.from({ length: 8 }).map((_, index) => (
                  <div
                    key={index}
                    className="overflow-hidden rounded-lg border border-slate-200 bg-white"
                  >
                    <div className="aspect-video animate-pulse bg-slate-200" />
                    <div className="space-y-2 p-2.5">
                      <div className="h-3 w-24 animate-pulse rounded bg-slate-200" />
                      <div className="h-2.5 w-16 animate-pulse rounded bg-slate-100" />
                    </div>
                  </div>
                ))}
              </div>
            ) : results.length > 0 ? (
              <div className="result-grid">
                {results.map((hit) => (
                  <ResultCard
                    key={`${hit.video_id}-${hit.shot_idx}-${hit.kf_uid ?? hit.start_ms}`}
                    hit={hit}
                    selected={isHitSelected(hit)}
                    showScore={!timelineSource}
                    onSelect={handleSelect}
                    onSimilar={handleSimilar}
                    onTimeline={handleTimeline}
                  />
                ))}
              </div>
            ) : (
              <div className="flex min-h-[320px] flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white/60 px-6 py-12 text-center">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 font-mono text-xs text-slate-400">
                  K
                </div>
                <p className="mt-3 text-sm font-medium text-slate-700">
                  {hasSearched ? 'Không có kết quả' : 'Chưa có truy vấn'}
                </p>
              </div>
            )}
          </div>
        </main>

        <aside
          aria-label="Preview và nộp bài"
          className="scroll-slim border-t border-slate-200 bg-[#fbfaf7] xl:min-h-0 xl:overflow-y-auto xl:border-t-0 xl:border-l"
        >
          <div className="space-y-4 p-4 sm:p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Preview</p>
                <h2 className="mt-1 truncate text-sm font-semibold text-slate-900">
                  {selected ? selected.video_id : 'Chưa chọn keyframe'}
                </h2>
                {selected && (
                  <p className="mt-0.5 text-xs text-slate-500">
                    shot {selected.shot_idx} · {formatMs(selected.start_ms)} →{' '}
                    {formatMs(selected.end_ms)}
                  </p>
                )}
              </div>
              {selected && activeFrame && (
                <span className="shrink-0 rounded border border-slate-300 bg-white px-2 py-1 font-mono text-[10px] text-slate-600">
                  {formatMs(activeFrame.ts_ms)}
                </span>
              )}
            </div>

            {selected ? (
              <div className="space-y-4">
                <VideoPanel
                  key={`${selected.video_id}-${selected.shot_idx}-${selected.start_ms}`}
                  hit={selected}
                  onActiveFrameChange={handleActiveFrame}
                />
                <DresPanel hit={selected} frame={activeFrame} />
              </div>
            ) : (
              <div className="flex min-h-[320px] flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white/60 px-6 py-12 text-center">
                <p className="text-sm font-medium text-slate-700">Chưa chọn keyframe</p>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}

export default App
