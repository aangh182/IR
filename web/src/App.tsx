import { useEffect, useState } from 'react'

type Health = {
  status: string
  version: string
  db: string
  db_ready: boolean
}

type Stats = {
  videos: number
  shots: number
  keyframes: number
  asr_segments: number
}

const STAT_LABELS: Array<[keyof Stats, string]> = [
  ['videos', 'Videos'],
  ['shots', 'Shots'],
  ['keyframes', 'Keyframes'],
  ['asr_segments', 'ASR segments'],
]

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      fetch('/api/health').then((res) => {
        if (!res.ok) throw new Error(`health: HTTP ${res.status}`)
        return res.json() as Promise<Health>
      }),
      fetch('/api/stats').then((res) => {
        if (!res.ok) throw new Error(`stats: HTTP ${res.status}`)
        return res.json() as Promise<Stats>
      }),
    ])
      .then(([healthData, statsData]) => {
        setHealth(healthData)
        setStats(statsData)
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  const online = health?.status === 'ok'

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500">AIC2024</p>
            <h1 className="text-2xl font-semibold">Known-Item Search</h1>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span
              className={`h-2 w-2 rounded-full ${
                online ? 'bg-emerald-400' : error ? 'bg-red-400' : 'bg-slate-500'
              }`}
            />
            <span className="text-slate-400">
              {error ? 'API offline' : online ? `API ${health?.version}` : 'Đang kiểm tra...'}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-10">
        <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-6">
          <label className="text-sm font-medium text-slate-300" htmlFor="query">
            Mô tả sự kiện
          </label>
          <div className="mt-2 flex gap-3">
            <input
              id="query"
              disabled
              placeholder="Phase 2: nhập mô tả tiếng Việt để tìm keyframe..."
              className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-400 placeholder:text-slate-600"
            />
            <button
              type="button"
              disabled
              className="rounded-lg bg-indigo-500/40 px-5 py-3 text-sm font-medium text-indigo-200"
            >
              Tìm
            </button>
          </div>
          <div className="mt-4 flex gap-2 text-xs text-slate-400">
            <span className="rounded-full border border-slate-700 px-3 py-1">Textual KIS</span>
            <span className="rounded-full border border-slate-700 px-3 py-1">Video KIS</span>
            <span className="rounded-full border border-slate-700 px-3 py-1">Q&amp;A</span>
          </div>
        </section>

        <section className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {STAT_LABELS.map(([key, label]) => (
            <div
              key={key}
              className="rounded-xl border border-slate-800 bg-slate-900/60 p-4"
            >
              <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
              <p className="mt-2 text-3xl font-semibold tabular-nums">
                {stats ? stats[key].toLocaleString('vi-VN') : '—'}
              </p>
            </div>
          ))}
        </section>

        <section className="mt-6 rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-sm text-slate-400">
          <p className="font-medium text-slate-300">Phase 0 · nền tảng</p>
          <p className="mt-2">
            Config, SQLite schema (append-only + compact), CLI và FastAPI đã sẵn sàng. Pipeline
            PySceneDetect → keyframe → CLIP → FAISS sẽ được nối ở Phase 1–2.
          </p>
          {error && <p className="mt-3 text-red-400">Lỗi kết nối API: {error}</p>}
          {health && (
            <p className="mt-3 font-mono text-xs text-slate-500">DB: {health.db}</p>
          )}
        </section>
      </main>
    </div>
  )
}

export default App
