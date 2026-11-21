import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { FilterPopover } from './components/FilterPopover'
import { ExamQueryDock } from './components/ExamQueryDock'
import { ChainCard } from './components/ChainCard'
import { ChainStrip } from './components/ChainStrip'
import { Icon } from './components/Icon'
import { MediaStage } from './components/MediaStage'
import type { MediaStageHandle } from './components/MediaStage'
import { ObjectFilterDrawer } from './components/ObjectFilterDrawer'
import { ResultCard } from './components/ResultCard'
import { ShortcutsDialog } from './components/ShortcutsDialog'
import { SubmitBar } from './components/SubmitBar'
import type { SubmitHandle } from './components/SubmitBar'
import { VideoKeyframeStrip } from './components/VideoKeyframeStrip'
import { formatMs } from './format'
import type {
  ChainHit,
  FrameOption,
  Health,
  Hit,
  ModelInfo,
  ObjectFacet,
  ObjectFilter,
  SearchResponse,
  SequentialResponse,
  Stats,
} from './types'
import { normalizeVideoShorthand, splitSequence } from './video'

const EXAMPLES = [
  'người phát biểu tại hội nghị',
  'xe màu đỏ chạy trên đường',
  'người dẫn chương trình đứng trước màn hình',
]

type RunOptions = {
  includeBoilerplate?: boolean
  dedup?: boolean
  topK?: number
  model?: string
  objects?: ObjectFilter[]
}

type ResultsSnapshot = {
  results: Hit[]
  elapsed: number | null
  lastQuery: string
  translatedQuery: string
  source: Hit
  videoSearchId: string | null
  filters: {
    includeBoilerplate: boolean
    dedup: boolean
    objectFilters: ObjectFilter[]
    topK: number
    selectedModel: string
  }
}

type SingleSnapshot = {
  selected: Hit | null
  elapsed: number | null
  lastQuery: string
  translatedQuery: string
  hasSearched: boolean
}

async function responseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // fall through to HTTP status
  }
  return `HTTP ${response.status}`
}

function serializeObjects(filters: ObjectFilter[]): string[] {
  return filters.map((item) =>
    item.minCount > 1 ? `${item.label}:${item.minCount}` : item.label,
  )
}

function framesOf(hit: Hit): FrameOption[] {
  if (hit.frames.length > 0) return hit.frames
  return [
    {
      ts_ms: hit.start_ms,
      start_ms: hit.start_ms,
      end_ms: hit.end_ms,
      url: hit.keyframe_url,
      is_keyframe: true,
    },
  ]
}

function keyframeIndex(hit: Hit): number {
  const index = framesOf(hit).findIndex((frame) => frame.is_keyframe)
  return index >= 0 ? index : 0
}

function keyframeTime(hit: Hit): number {
  return framesOf(hit).find((frame) => frame.is_keyframe)?.ts_ms ?? hit.start_ms
}

function hitKey(hit: Hit): string {
  return `${hit.video_id}-${hit.shot_idx}-${hit.kf_uid ?? hit.start_ms}`
}

function isSameHit(left: Hit, right: Hit): boolean {
  if (left.kf_uid !== null && right.kf_uid !== null) {
    return left.kf_uid === right.kf_uid
  }
  return left.video_id === right.video_id && left.shot_idx === right.shot_idx
}

function chainKey(chain: ChainHit): string {
  return `${chain.video_id}-${chain.start_ms}-${chain.score.toFixed(4)}`
}

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)

  const [query, setQuery] = useState('')
  const queryRef = useRef<HTMLInputElement | null>(null)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const mediaRef = useRef<MediaStageHandle | null>(null)
  const submitRef = useRef<SubmitHandle | null>(null)

  const [topK, setTopK] = useState(20)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [objectFilters, setObjectFilters] = useState<ObjectFilter[]>([])
  const [objectDrawerOpen, setObjectDrawerOpen] = useState(false)
  const [objectOptions, setObjectOptions] = useState<ObjectFacet[]>([])
  const [includeBoilerplate, setIncludeBoilerplate] = useState(false)
  const [dedup, setDedup] = useState(true)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const [dresRevision, setDresRevision] = useState(0)

  const [results, setResults] = useState<Hit[]>([])
  const [selected, setSelected] = useState<Hit | null>(null)
  const [activeFrameIndex, setActiveFrameIndex] = useState<number | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastQuery, setLastQuery] = useState('')
  const [translatedQuery, setTranslatedQuery] = useState('')
  const [similarSource, setSimilarSource] = useState<Hit | null>(null)
  const [timelineSource, setTimelineSource] = useState<Hit | null>(null)
  const [videoSearchId, setVideoSearchId] = useState<string | null>(null)
  const [videoQuery, setVideoQuery] = useState('')
  const [previousResults, setPreviousResults] = useState<ResultsSnapshot | null>(null)
  const [sequentialMode, setSequentialMode] = useState(false)
  const [chains, setChains] = useState<ChainHit[]>([])
  const [selectedChain, setSelectedChain] = useState<ChainHit | null>(null)
  const [sequentialQueries, setSequentialQueries] = useState<string[]>([])
  const [singleSnapshot, setSingleSnapshot] = useState<SingleSnapshot | null>(null)

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
    if (!selected) return
    const target = document.querySelector(`[data-hit-key="${hitKey(selected)}"]`)
    target?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [selected])

  useEffect(() => {
    if (!selectedChain) return
    const target = document.querySelector(`[data-chain-key="${chainKey(selectedChain)}"]`)
    target?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [selectedChain])

  const online = health?.status === 'ok'
  const indexReady = health?.index_ready === true
  const selectedModelInfo = models.find((item) => item.name === selectedModel) ?? null
  const defaultModelName = models.find((item) => item.default)?.name ?? models[0]?.name ?? ''
  const keyframeCount = selectedModelInfo?.keyframes ?? health?.index_count ?? 0

  const selectedFrames = selected ? framesOf(selected) : []
  const selectedKeyframeIndex = selected ? keyframeIndex(selected) : 0
  const activeIndex = selected
    ? Math.min(
        activeFrameIndex ?? selectedKeyframeIndex,
        Math.max(0, selectedFrames.length - 1),
      )
    : 0
  const activeFrame = selected ? (selectedFrames[activeIndex] ?? null) : null
  const resolvedVideoId = normalizeVideoShorthand(videoQuery)

  const modelChanged =
    Boolean(selectedModel) && selectedModel !== defaultModelName
  const filtersActive =
    objectFilters.length > 0 ||
    includeBoilerplate ||
    !dedup ||
    topK !== 20 ||
    modelChanged
  const filterCount =
    objectFilters.length +
    (includeBoilerplate ? 1 : 0) +
    (!dedup ? 1 : 0) +
    (topK !== 20 ? 1 : 0) +
    (modelChanged ? 1 : 0)

  const resultsLabel = loading
    ? 'Đang tìm...'
    : sequentialMode
      ? `${chains.length} chuỗi`
      : hasSearched
        ? `${results.length} ${
            similarSource
              ? 'frame tương tự'
              : timelineSource
                ? 'keyframe lân cận'
                : videoSearchId
                  ? `keyframe · ${videoSearchId}`
                  : 'keyframe'
          }`
        : 'Kết quả'

  function focusStage() {
    window.requestAnimationFrame(() => {
      queryRef.current?.blur()
      stageRef.current?.focus()
    })
  }

  function exitSequentialMode() {
    if (loading) return
    const snapshot = singleSnapshot
    setSequentialMode(false)
    setChains([])
    setSelectedChain(null)
    setSequentialQueries([])
    setError(null)
    setSingleSnapshot(null)
    if (!snapshot) return
    setSelected(snapshot.selected)
    setElapsed(snapshot.elapsed)
    setLastQuery(snapshot.lastQuery)
    setTranslatedQuery(snapshot.translatedQuery)
    setHasSearched(snapshot.hasSearched)
    setActiveFrameIndex(null)
  }

  function toggleSequential() {
    if (loading) return
    if (sequentialMode) {
      exitSequentialMode()
      return
    }
    setSingleSnapshot({
      selected,
      elapsed,
      lastQuery,
      translatedQuery,
      hasSearched,
    })
    setSequentialMode(true)
    setChains([])
    setSelectedChain(null)
    setSequentialQueries([])
    setError(null)
  }

  function selectChain(chain: ChainHit) {
    setSelectedChain(chain)
    setSelected(chain.events[0]?.hit ?? null)
    setActiveFrameIndex(null)
  }

  function moveChainSelection(delta: number) {
    if (!sequentialMode || chains.length === 0) return
    const current = selectedChain ? chains.indexOf(selectedChain) : -1
    const base = current === -1 ? 0 : current
    const next = Math.max(0, Math.min(chains.length - 1, base + delta))
    if (next === current) return
    selectChain(chains[next])
  }

  async function runSequential(queries: string[]) {
    if (loading) return
    const cleaned = queries
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 6)
    if (cleaned.length < 2) {
      setError('Cần ít nhất 2 sự kiện, phân tách bằng →.')
      return
    }
    if (!sequentialMode) {
      setSingleSnapshot({
        selected,
        elapsed,
        lastQuery,
        translatedQuery,
        hasSearched,
      })
      setSequentialMode(true)
    }

    setLoading(true)
    setError(null)
    setSequentialQueries(cleaned)
    setChains([])
    setSelectedChain(null)

    try {
      const response = await fetch('/api/sequential', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          queries: cleaned,
          top_k: topK,
          model: selectedModel || undefined,
          fuse_models: true,
          include_boilerplate: includeBoilerplate,
          objects: cleaned.map(() => serializeObjects(objectFilters)),
        }),
      })
      if (!response.ok) throw new Error(await responseError(response))

      const data = (await response.json()) as SequentialResponse
      setChains(data.chains)
      const first = data.chains[0] ?? null
      setSelectedChain(first)
      setSelected(first?.events[0]?.hit ?? null)
      setActiveFrameIndex(null)
      setElapsed(data.elapsed_ms)
      setLastQuery(cleaned.join(' → '))
      setTranslatedQuery('')
      setHasSearched(true)
      focusStage()
    } catch (err) {
      setChains([])
      setSelectedChain(null)
      setSelected(null)
      setActiveFrameIndex(null)
      setElapsed(null)
      setError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setLoading(false)
    }
  }

  async function runSearch(text: string, options: RunOptions = {}) {
    const trimmed = text.trim()
    if (!trimmed || loading) return
    if (sequentialMode) exitSequentialMode()

    const showBoilerplate = options.includeBoilerplate ?? includeBoilerplate
    const useDedup = options.dedup ?? dedup
    const useTopK = options.topK ?? topK
    const useModel = options.model ?? selectedModel
    const useObjects = options.objects ?? objectFilters

    setLoading(true)
    setError(null)
    setHasSearched(true)
    setSimilarSource(null)
    setTimelineSource(null)
    setVideoSearchId(null)
    setVideoQuery('')
    setPreviousResults(null)
    setLastQuery(trimmed)
    setTranslatedQuery('')

    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: trimmed,
          top_k: useTopK,
          objects: serializeObjects(useObjects),
          model: useModel || undefined,
          include_boilerplate: showBoilerplate,
          dedup: useDedup,
        }),
      })
      if (!response.ok) throw new Error(await responseError(response))

      const data = (await response.json()) as SearchResponse
      setResults(data.results)
      setSelected(data.results[0] ?? null)
      setActiveFrameIndex(null)
      setTranslatedQuery(data.translated_query ?? '')
      setElapsed(data.elapsed_ms)
      focusStage()
    } catch (err) {
      setResults([])
      setSelected(null)
      setActiveFrameIndex(null)
      setElapsed(null)
      setError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setLoading(false)
    }
  }

  async function runSimilar(hit: Hit, options: RunOptions = {}) {
    if (loading) return
    if (sequentialMode) exitSequentialMode()
    if (!hit.kf_uid) {
      setError('Frame này không có kf_uid trong index.')
      return
    }

    const showBoilerplate = options.includeBoilerplate ?? includeBoilerplate
    const useDedup = options.dedup ?? dedup
    const useTopK = options.topK ?? topK
    const useModel = options.model ?? selectedModel
    const useObjects = options.objects ?? objectFilters

    if (!similarSource && !timelineSource) {
      setPreviousResults({
        results,
        elapsed,
        lastQuery,
        translatedQuery,
        source: hit,
        videoSearchId,
        filters: {
          includeBoilerplate,
          dedup,
          objectFilters,
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
    setVideoSearchId(null)
    setVideoQuery('')
    setLastQuery('')
    setTranslatedQuery('')

    try {
      const response = await fetch('/api/similar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kf_uid: hit.kf_uid,
          top_k: useTopK,
          objects: serializeObjects(useObjects),
          model: useModel || undefined,
          include_boilerplate: showBoilerplate,
          dedup: useDedup,
        }),
      })
      if (!response.ok) throw new Error(await responseError(response))

      const data = (await response.json()) as SearchResponse
      setResults(data.results)
      setSelected(data.results[0] ?? null)
      setActiveFrameIndex(null)
      setElapsed(data.elapsed_ms)
      focusStage()
    } catch (err) {
      setResults([])
      setSelected(null)
      setActiveFrameIndex(null)
      setElapsed(null)
      setError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setLoading(false)
    }
  }

  async function runTimeline(hit: Hit) {
    if (loading) return
    if (sequentialMode) exitSequentialMode()
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
        videoSearchId,
        filters: {
          includeBoilerplate,
          dedup,
          objectFilters,
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
    setVideoSearchId(null)
    setVideoQuery('')
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
      setActiveFrameIndex(null)
      setElapsed(data.elapsed_ms)
      focusStage()
    } catch (err) {
      setResults([])
      setSelected(null)
      setActiveFrameIndex(null)
      setElapsed(null)
      setError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setLoading(false)
    }
  }

  async function runVideoSearch(videoId: string) {
    if (loading) return
    if (sequentialMode) exitSequentialMode()

    setLoading(true)
    setError(null)
    setHasSearched(true)
    setSimilarSource(null)
    setTimelineSource(null)
    setVideoSearchId(videoId)
    setVideoQuery(videoId)
    setPreviousResults(null)
    setLastQuery(videoId)
    setTranslatedQuery('')

    try {
      const response = await fetch(
        `/api/videos/${encodeURIComponent(videoId)}/keyframes`,
      )
      if (!response.ok) throw new Error(await responseError(response))

      const data = (await response.json()) as SearchResponse
      setResults(data.results)
      setSelected(data.results[0] ?? null)
      setActiveFrameIndex(null)
      setElapsed(data.elapsed_ms)
      focusStage()
    } catch (err) {
      setResults([])
      setSelected(null)
      setActiveFrameIndex(null)
      setElapsed(null)
      setError(err instanceof Error ? err.message : 'Lỗi không xác định')
    } finally {
      setLoading(false)
    }
  }

  function submitVideoSearch() {
    const normalized = normalizeVideoShorthand(videoQuery) ?? videoQuery.trim()
    if (!normalized) {
      setError('Nhập mã video trước khi tìm.')
      return
    }
    setVideoQuery(normalized)
    void runVideoSearch(normalized)
  }

  function useExamQuery(text: string) {
    if (!text.trim()) return
    setQuery(text)
    setError(null)
    if (filtersOpen) setFiltersOpen(false)
    if (sequentialMode) {
      const queries = splitSequence(text)
      if (queries.length < 2) {
        setError('Cần ít nhất 2 sự kiện, phân tách bằng →.')
        return
      }
      void runSequential(queries)
      return
    }
    void runSearch(text)
  }

  function runCurrent(options: RunOptions = {}) {
    if (loading) return
    if (similarSource) {
      void runSimilar(similarSource, options)
      return
    }
    if (timelineSource) {
      void runTimeline(timelineSource)
      return
    }
    if (videoSearchId) {
      void runVideoSearch(videoSearchId)
      return
    }
    if (sequentialMode) {
      if (sequentialQueries.length >= 2) void runSequential(sequentialQueries)
      return
    }
    if (query.trim()) void runSearch(query, options)
  }

  function submitSearch() {
    const trimmed = query.trim()
    if (!trimmed) {
      setError(
        sequentialMode
          ? 'Nhập chuỗi sự kiện, phân tách bằng →.'
          : 'Nhập mô tả sự kiện trước khi tìm.',
      )
      queryRef.current?.focus()
      return
    }
    if (filtersOpen) setFiltersOpen(false)
    if (sequentialMode) {
      const queries = splitSequence(trimmed)
      if (queries.length < 2) {
        setError('Cần ít nhất 2 sự kiện, phân tách bằng →.')
        return
      }
      void runSequential(queries)
      return
    }
    void runSearch(trimmed)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submitSearch()
  }

  const handleSelect = useCallback((hit: Hit) => {
    setSelected(hit)
    setActiveFrameIndex(null)
  }, [])

  function handleSimilar(hit: Hit) {
    void runSimilar(hit)
  }

  function handleTimeline(hit: Hit) {
    void runTimeline(hit)
  }

  const backToResults = useCallback(() => {
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
    setActiveFrameIndex(null)
    setElapsed(snapshot.elapsed)
    setLastQuery(snapshot.lastQuery)
    setTranslatedQuery(snapshot.translatedQuery)
    setVideoSearchId(snapshot.videoSearchId)
    setVideoQuery(snapshot.videoSearchId ?? '')
    setIncludeBoilerplate(snapshot.filters.includeBoilerplate)
    setDedup(snapshot.filters.dedup)
    setObjectFilters(snapshot.filters.objectFilters)
    setTopK(snapshot.filters.topK)
    setSelectedModel(snapshot.filters.selectedModel)
  }, [loading, previousResults])

  function removeObject(label: string) {
    const next = objectFilters.filter((item) => item.label !== label)
    setObjectFilters(next)
    runCurrent({ objects: next })
  }

  function applyObjectFilters() {
    setObjectDrawerOpen(false)
    runCurrent({ objects: objectFilters })
  }

  function resetFilters() {
    const nextModel = defaultModelName
    setObjectFilters([])
    setIncludeBoilerplate(false)
    setDedup(true)
    setTopK(20)
    setSelectedModel(nextModel)
    setError(null)
    runCurrent({
      objects: [],
      includeBoilerplate: false,
      dedup: true,
      topK: 20,
      model: nextModel,
    })
  }

  function changeModel(next: string) {
    setSelectedModel(next)
    runCurrent({ model: next })
  }

  function changeTopK(next: number) {
    setTopK(next)
    runCurrent({ topK: next })
  }

  function changeBoilerplate(next: boolean) {
    setIncludeBoilerplate(next)
    runCurrent({ includeBoilerplate: next })
  }

  function changeDedup(next: boolean) {
    setDedup(next)
    runCurrent({ dedup: next })
  }

  function openObjectDrawer() {
    setFiltersOpen(false)
    setObjectDrawerOpen(true)
  }

  const closeObjectDrawer = useCallback(() => setObjectDrawerOpen(false), [])
  const handleDresRevision = useCallback(() => setDresRevision((value) => value + 1), [])

  function moveSelection(delta: number) {
    if (results.length === 0) return
    const current = selected
      ? results.findIndex((item) => isSameHit(item, selected))
      : -1
    const base = current === -1 ? 0 : current
    const next = Math.max(0, Math.min(results.length - 1, base + delta))
    if (next === current) return
    handleSelect(results[next])
  }

  function stepFrame(delta: number) {
    if (!selected) return
    const frames = framesOf(selected)
    const current = activeFrameIndex ?? keyframeIndex(selected)
    const next = Math.max(0, Math.min(frames.length - 1, current + delta))
    setActiveFrameIndex(next)
  }

  function isHitSelected(hit: Hit): boolean {
    return selected ? isSameHit(hit, selected) : false
  }

  const keyHandlerRef = useRef<(event: KeyboardEvent) => void>(() => {})

  function onKeyDown(event: KeyboardEvent) {
    if (event.defaultPrevented) return
    const target = event.target as HTMLElement | null
    const typing = Boolean(
      target?.closest('input, textarea, select, [contenteditable="true"]'),
    )

    if (event.key === '/' && !typing) {
      event.preventDefault()
      queryRef.current?.focus()
      queryRef.current?.select()
      return
    }

    if (event.key === 'Escape') {
      if (shortcutsOpen) {
        setShortcutsOpen(false)
        return
      }
      if (filtersOpen) {
        setFiltersOpen(false)
        return
      }
      if (objectDrawerOpen) return
      if (sequentialMode) {
        event.preventDefault()
        exitSequentialMode()
        return
      }
      if (similarSource || timelineSource) {
        event.preventDefault()
        backToResults()
      }
      return
    }

    if (shortcutsOpen || filtersOpen || objectDrawerOpen) return
    if (typing) return
    if (event.metaKey || event.ctrlKey || event.altKey) return

    switch (event.key) {
      case '?':
        event.preventDefault()
        setShortcutsOpen(true)
        break
      case 'ArrowRight':
        event.preventDefault()
        if (sequentialMode) moveChainSelection(1)
        else moveSelection(1)
        break
      case 'ArrowLeft':
        event.preventDefault()
        if (sequentialMode) moveChainSelection(-1)
        else moveSelection(-1)
        break
      case 'ArrowDown':
        event.preventDefault()
        if (sequentialMode) moveChainSelection(2)
        else moveSelection(2)
        break
      case 'ArrowUp':
        event.preventDefault()
        if (sequentialMode) moveChainSelection(-2)
        else moveSelection(-2)
        break
      case ' ':
        event.preventDefault()
        mediaRef.current?.togglePlay()
        break
      case 's':
      case 'S':
        event.preventDefault()
        submitRef.current?.submit()
        break
      case 'c':
      case 'C':
        event.preventDefault()
        void submitRef.current?.copy()
        break
      case '[':
        event.preventDefault()
        stepFrame(-1)
        break
      case ']':
        event.preventDefault()
        stepFrame(1)
        break
      case 'f':
      case 'F':
        event.preventDefault()
        setFiltersOpen((value) => !value)
        break
      case 'r':
      case 'R':
        event.preventDefault()
        if (selected) handleSimilar(selected)
        break
      case 't':
      case 'T':
        event.preventDefault()
        if (selected) handleTimeline(selected)
        break
      default:
        break
    }
  }

  useEffect(() => {
    keyHandlerRef.current = onKeyDown
  })

  useEffect(() => {
    const listener = (event: KeyboardEvent) => keyHandlerRef.current(event)
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  }, [])

  const statusTitle = [
    selectedModelInfo
      ? `${selectedModelInfo.name} · ${selectedModelInfo.dim}d`
      : null,
    health?.loaded_models?.length
      ? `${health.loaded_models.join(', ')} đã nạp`
      : null,
    stats ? `${stats.videos.toLocaleString('vi-VN')} video · ${stats.keyframes.toLocaleString('vi-VN')} keyframe` : null,
    statusError,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <div className="min-h-dvh bg-[#f7f7f5] text-slate-900 laptop:flex laptop:h-dvh laptop:flex-col laptop:overflow-hidden">
      <header className="sticky top-0 z-30 shrink-0 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-[1800px] items-center gap-2 px-3 sm:gap-3 sm:px-5">
          <div className="flex shrink-0 items-center gap-2">
            <div aria-hidden="true" className="grid h-8 w-8 place-items-center rounded-lg bg-slate-900">
              <span className="grid grid-cols-2 gap-[3px]">
                <span className="h-1.5 w-1.5 rounded-[1px] bg-white" />
                <span className="h-1.5 w-1.5 rounded-[1px] bg-white" />
                <span className="h-1.5 w-1.5 rounded-[1px] bg-white" />
                <span className="h-1.5 w-1.5 rounded-[1px] bg-white" />
              </span>
            </div>
            <span className="hidden text-sm font-semibold tracking-tight text-slate-900 sm:inline">
              Mage<span className="font-normal text-slate-500">seeker</span>
            </span>
          </div>

          <form onSubmit={handleSubmit} autoComplete="off" className="flex min-w-0 flex-1 items-center gap-2">
            <div className="relative min-w-0 flex-1">
              <Icon
                name="search"
                className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
              />
              <input
                ref={queryRef}
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value)
                  if (error) setError(null)
                }}
                onKeyDown={(event) => {
                  if (
                    !sequentialMode ||
                    event.key !== 'Enter' ||
                    !event.shiftKey ||
                    event.nativeEvent.isComposing
                  ) {
                    return
                  }
                  event.preventDefault()
                  const input = event.currentTarget
                  const start = input.selectionStart ?? query.length
                  const end = input.selectionEnd ?? start
                  const before = query.slice(0, start)
                  const after = query.slice(end)
                  const insert = before.trim() ? ' → ' : ''
                  const next = `${before}${insert}${after}`
                  setQuery(next)
                  if (error) setError(null)
                  window.requestAnimationFrame(() => {
                    const position = before.length + insert.length
                    input.setSelectionRange(position, position)
                    input.focus()
                  })
                }}
                type="search"
                enterKeyHint="search"
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="off"
                spellCheck={false}
                placeholder={
                  sequentialMode
                    ? 'Sự kiện 1 · Shift+Enter để thêm'
                    : 'Mô tả sự kiện...'
                }
                title={
                  sequentialMode
                    ? 'Shift+Enter để tách sự kiện, Enter để tìm'
                    : undefined
                }
                aria-label={sequentialMode ? 'Chuỗi sự kiện' : 'Mô tả sự kiện'}
                className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50/70 pl-9 pr-10 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-500 hover:border-slate-300 focus:border-blue-600 focus:bg-white focus:ring-2 focus:ring-blue-600/15"
              />
              <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border border-slate-200 bg-white px-1 py-0.5 font-mono text-[10px] text-slate-500 sm:block">
                /
              </kbd>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="flex h-10 shrink-0 items-center gap-2 rounded-lg bg-blue-600 px-3 text-sm font-semibold text-white transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 disabled:cursor-wait disabled:bg-slate-300 sm:px-4"
            >
              {loading && (
                <span
                  aria-hidden="true"
                  className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
                />
              )}
              <span className="hidden sm:inline">{loading ? 'Đang tìm' : 'Tìm'}</span>
              <span className="sm:hidden">{loading ? '' : 'Tìm'}</span>
            </button>
            <button
              type="button"
              onClick={toggleSequential}
              disabled={loading}
              aria-pressed={sequentialMode}
              title="Tìm chuỗi sự kiện (A → B → C)"
              className={`flex h-10 shrink-0 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 disabled:cursor-not-allowed disabled:opacity-50 ${
                sequentialMode
                  ? 'border-blue-600 bg-blue-50 text-blue-800'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
              }`}
            >
              <Icon name="timeline" className="h-3.5 w-3.5" />
              <span>Chuỗi</span>
            </button>
          </form>

          <span
            title={statusTitle}
            className="hidden shrink-0 items-center gap-1.5 text-xs text-slate-500 md:flex"
          >
            <span
              aria-hidden="true"
              className={`h-1.5 w-1.5 rounded-full ${
                statusError
                  ? 'bg-red-500'
                  : indexReady
                    ? 'bg-blue-500'
                    : online
                      ? 'bg-amber-500'
                      : 'bg-slate-400'
              }`}
            />
            {statusError
              ? 'API lỗi'
              : indexReady
                ? `${keyframeCount.toLocaleString('vi-VN')} kf`
                : online
                  ? 'Chưa có index'
                  : 'Đang kết nối'}
          </span>

          <button
            type="button"
            onClick={() => setFiltersOpen((value) => !value)}
            aria-expanded={filtersOpen}
            aria-label="Bộ lọc"
            className={`relative flex h-9 shrink-0 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 ${
              filtersOpen || filtersActive
                ? 'border-blue-200 bg-blue-50 text-blue-800'
                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
            }`}
          >
            <Icon name="filter" className="h-4 w-4" />
            <span className="hidden sm:inline">Bộ lọc</span>
            {filterCount > 0 && (
              <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-blue-600 px-1 font-mono text-[9px] font-semibold text-white">
                {filterCount}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => setShortcutsOpen(true)}
            aria-label="Phím tắt"
            title="Phím tắt (?)"
            className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-colors hover:border-slate-300 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 sm:flex"
          >
            <Icon name="keyboard" className="h-4 w-4" />
          </button>
        </div>
        {loading && (
          <div className="h-0.5 w-full overflow-hidden bg-blue-100">
            <div className="h-full w-1/2 animate-pulse bg-blue-600" />
          </div>
        )}
      </header>

      {!hasSearched && !query && (
        <div className="shrink-0 border-b border-slate-100 bg-white px-3 py-1.5 sm:px-5">
          <div className="mx-auto flex w-full max-w-[1800px] items-center gap-2 overflow-x-auto">
            <span className="shrink-0 text-[11px] text-slate-500">Thử:</span>
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setQuery(example)
                  void runSearch(example)
                }}
                className="shrink-0 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      )}

      {translatedQuery && translatedQuery !== lastQuery && (
        <div className="shrink-0 border-b border-slate-100 bg-white px-3 py-1.5 sm:px-5">
          <p className="mx-auto w-full max-w-[1800px] truncate text-[11px] text-slate-500">
            <span className="text-slate-500">Dịch:</span> {translatedQuery}
          </p>
        </div>
      )}

      <div className="mx-auto flex w-full max-w-[1800px] flex-1 min-h-0 flex-col px-3 pb-40 pt-3 sm:px-5 laptop:pb-20">
        {error && (
          <div
            role="alert"
            className="mb-2 flex shrink-0 items-start justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800"
          >
            <span className="min-w-0">{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              aria-label="Đóng lỗi"
              className="shrink-0 text-red-700/70 transition-colors hover:text-red-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
            >
              <Icon name="close" className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        <div className="grid min-h-0 grid-cols-1 gap-3 laptop:flex-1 laptop:grid-cols-[minmax(0,1fr)_minmax(420px,36%)]">
          <div
            ref={stageRef}
            tabIndex={-1}
            className="scroll-slim flex min-h-0 flex-col outline-none laptop:overflow-y-auto laptop:pr-1"
          >
            {selected ? (
              <>
                <MediaStage
                  ref={mediaRef}
                  hit={selected}
                  frames={selectedFrames}
                  activeIndex={activeIndex}
                  compact={sequentialMode && Boolean(selectedChain)}
                  onSelectFrame={setActiveFrameIndex}
                  onSimilar={() => handleSimilar(selected)}
                  onTimeline={() => handleTimeline(selected)}
                />
                {sequentialMode && selectedChain && (
                  <ChainStrip
                    chain={selectedChain}
                    activeKfUid={selected?.kf_uid ?? null}
                    onSelect={handleSelect}
                  />
                )}
                <VideoKeyframeStrip
                  key={selected.video_id}
                  videoId={selected.video_id}
                  activeKfUid={selected.kf_uid}
                  onSelect={handleSelect}
                />
              </>
            ) : loading ? (
              <div className="my-auto space-y-2" aria-busy="true">
                <div className="aspect-video w-full animate-pulse rounded-xl bg-slate-200/70" />
                <div className="h-3 w-40 animate-pulse rounded bg-slate-200/70" />
                <div className="flex gap-1.5">
                  {Array.from({ length: 8 }).map((_, index) => (
                    <div key={index} className="h-14 w-24 animate-pulse rounded-lg bg-slate-200/70" />
                  ))}
                </div>
              </div>
            ) : (
              <div className="my-auto flex w-full max-w-xl flex-col items-center px-6 py-12 text-center">
                <Icon name="search" className="h-6 w-6 text-slate-500" />
                <p className="mt-3 text-sm font-medium text-slate-700">
                  {hasSearched ? 'Không tìm thấy keyframe' : 'Nhập mô tả sự kiện để tìm keyframe'}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {hasSearched
                    ? 'Thử mô tả khác, hoặc bỏ bớt bộ lọc.'
                    : 'Enter để tìm · / để quay lại ô tìm kiếm'}
                </p>
                {statusError && (
                  <p className="mt-4 max-w-md text-xs text-red-700">
                    Không kết nối được API: {statusError}
                  </p>
                )}
                {health && !indexReady && !statusError && (
                  <p className="mt-4 max-w-md text-xs text-amber-700">
                    Index chưa sẵn sàng. Chạy import shard trước khi tìm.
                  </p>
                )}
              </div>
            )}
          </div>

          <aside
            aria-label="Kết quả tìm kiếm"
            className="scroll-slim min-h-0 laptop:overflow-y-auto laptop:border-l laptop:border-slate-200 laptop:pl-3"
          >
            {sequentialMode && (
              <div className="mb-2 flex items-center justify-between gap-2 rounded-lg border border-blue-200 bg-blue-50 px-2 py-1.5">
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold text-blue-900">
                    Chuỗi sự kiện · {sequentialQueries.length} sự kiện
                  </p>
                  <p className="truncate text-[10px] text-blue-800">
                    {sequentialQueries.join(' → ') || 'Nhập chuỗi ở ô tìm kiếm'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={exitSequentialMode}
                  disabled={loading}
                  className="shrink-0 rounded-md bg-white px-2 py-1 text-[11px] font-medium text-blue-800 transition-colors hover:bg-blue-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Tắt chuỗi
                </button>
              </div>
            )}

            <div className="mb-2 flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white p-1.5">
              <label
                htmlFor="video-lookup"
                className="flex shrink-0 items-center gap-1 pl-1 text-[11px] font-medium text-slate-600"
              >
                <Icon name="video" className="h-3.5 w-3.5 text-slate-500" />
                Mã video
              </label>
              <input
                id="video-lookup"
                value={videoQuery}
                onChange={(event) => setVideoQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key !== 'Enter') return
                  event.preventDefault()
                  submitVideoSearch()
                }}
                placeholder="12 016"
                aria-label="Tìm theo mã video"
                spellCheck={false}
                className="h-8 min-w-0 flex-1 rounded-md bg-slate-50 px-2 font-mono text-xs text-slate-900 outline-none transition-colors placeholder:text-slate-500 focus:bg-white focus:ring-2 focus:ring-blue-600/20"
              />
              {resolvedVideoId && resolvedVideoId !== videoQuery.trim() && (
                <span className="shrink-0 font-mono text-[10px] text-slate-500">
                  → {resolvedVideoId}
                </span>
              )}
              <button
                type="button"
                onClick={submitVideoSearch}
                disabled={loading}
                className="h-8 shrink-0 rounded-md bg-blue-600 px-2.5 text-[11px] font-semibold text-white transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 disabled:cursor-wait disabled:opacity-50"
              >
                Tìm
              </button>
            </div>

            <div className="flex items-center justify-between gap-2 pb-2">
              <div className="flex min-w-0 items-baseline gap-2">
                <h2 className="truncate text-xs font-semibold text-slate-700">
                  {resultsLabel}
                </h2>
                {elapsed !== null && (
                  <span className="shrink-0 font-mono text-[10px] text-slate-500 tabular-nums">
                    {elapsed} ms
                  </span>
                )}
              </div>
              <span className="hidden shrink-0 text-[10px] text-slate-500 sm:inline">
                ↑↓ chọn
              </span>
            </div>

            {(similarSource || timelineSource) && (
              <div className="mb-2 flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-2 py-1.5">
                <img
                  src={(similarSource ?? timelineSource)!.keyframe_url}
                  alt=""
                  className="h-8 w-14 shrink-0 rounded object-cover"
                />
                <p className="min-w-0 flex-1 truncate text-[11px] text-blue-900">
                  <span className="font-medium">
                    {similarSource ? 'Tương tự' : 'Lân cận'}
                  </span>{' '}
                  <span className="font-mono">
                    {(similarSource ?? timelineSource)!.video_id}
                  </span>{' '}
                  · {formatMs(keyframeTime((similarSource ?? timelineSource)!))}
                </p>
                <button
                  type="button"
                  onClick={backToResults}
                  disabled={loading}
                  className="shrink-0 rounded-md bg-white px-2 py-1 text-[11px] font-medium text-blue-800 transition-colors hover:bg-blue-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 disabled:opacity-50"
                >
                  ← Quay lại
                </button>
              </div>
            )}

            {sequentialMode ? (
              loading ? (
                <div className="results-grid" aria-busy="true">
                  {Array.from({ length: 4 }).map((_, index) => (
                    <div
                      key={index}
                      className="aspect-video animate-pulse rounded-xl bg-slate-200/70"
                    />
                  ))}
                </div>
              ) : chains.length > 0 ? (
                <div className="results-grid">
                  {chains.map((chain) => (
                    <ChainCard
                      key={chainKey(chain)}
                      chain={chain}
                      selected={selectedChain === chain}
                      onSelect={selectChain}
                    />
                  ))}
                </div>
              ) : (
                <div className="px-1 py-8 text-center">
                  <p className="text-xs text-slate-500">
                    {hasSearched
                      ? 'Không có chuỗi.'
                      : 'Bật chuỗi, nhập các sự kiện bằng → rồi Tìm.'}
                  </p>
                  {sequentialQueries.length >= 2 && (
                    <p className="mt-1 text-[11px] text-slate-500">
                      {sequentialQueries.join(' → ')}
                    </p>
                  )}
                </div>
              )
            ) : results.length > 0 ? (
              <div className="results-grid">
                {results.map((hit) => (
                  <ResultCard
                    key={hitKey(hit)}
                    hit={hit}
                    selected={isHitSelected(hit)}
                    showScore={!timelineSource && !videoSearchId}
                    onSelect={handleSelect}
                    onSimilar={handleSimilar}
                    onTimeline={handleTimeline}
                  />
                ))}
              </div>
            ) : loading ? (
              <div className="results-grid" aria-busy="true">
                {Array.from({ length: 6 }).map((_, index) => (
                  <div key={index} className="aspect-video animate-pulse rounded-xl bg-slate-200/70" />
                ))}
              </div>
            ) : (
              <div className="px-1 py-8 text-center">
                <p className="text-xs text-slate-500">
                  {hasSearched ? 'Không có kết quả.' : 'Kết quả sẽ hiện ở đây.'}
                </p>
                {hasSearched && (
                  <button
                    type="button"
                    onClick={() => queryRef.current?.focus()}
                    className="mt-2 text-[11px] font-medium text-blue-700 transition-colors hover:text-blue-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
                  >
                    Thử mô tả khác
                  </button>
                )}
              </div>
            )}

            {(results.length > 0 || chains.length > 0) && (
              <div
                aria-hidden="true"
                className="pointer-events-none sticky bottom-0 -mt-8 h-8 bg-gradient-to-t from-[#f7f7f5] to-transparent"
              />
            )}
          </aside>
        </div>
      </div>

      <SubmitBar
        ref={submitRef}
        hit={selected}
        frame={activeFrame}
        onEvaluationChange={handleDresRevision}
        queryControl={
          <ExamQueryDock
            onUseQuery={useExamQuery}
            refreshKey={dresRevision}
            sequential={sequentialMode}
          />
        }
      />

      <FilterPopover
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        models={models}
        selectedModel={selectedModel}
        onModelChange={changeModel}
        topK={topK}
        onTopKChange={changeTopK}
        includeBoilerplate={includeBoilerplate}
        onBoilerplateChange={changeBoilerplate}
        dedup={dedup}
        onDedupChange={changeDedup}
        objectFilters={objectFilters}
        onRemoveObject={removeObject}
        onOpenObjects={openObjectDrawer}
        onReset={resetFilters}
        isDefault={!filtersActive}
      />

      <ShortcutsDialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />

      <ObjectFilterDrawer
        open={objectDrawerOpen}
        facets={objectOptions}
        filters={objectFilters}
        onClose={closeObjectDrawer}
        onApply={applyObjectFilters}
        onChange={setObjectFilters}
      />
    </div>
  )
}

export default App
