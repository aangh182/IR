import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'

import { formatMs } from '../format'
import type { FrameOption, Hit } from '../types'
import { Icon } from './Icon'
import { ImageLightbox } from './ImageLightbox'

export type MediaStageHandle = {
  togglePlay: () => void
}

type Props = {
  hit: Hit
  frames: FrameOption[]
  activeIndex: number
  compact?: boolean
  onSelectFrame: (index: number) => void
  onSimilar: () => void
  onTimeline: () => void
}

function objectLabel(hit: Hit, label: string): string {
  const count = hit.evidence.object_counts[label] ?? 0
  return count > 1 ? `${label} ×${count}` : label
}

export const MediaStage = forwardRef<MediaStageHandle, Props>(function MediaStage(
  { hit, frames, activeIndex, compact = false, onSelectFrame, onSimilar, onTimeline },
  ref,
) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const playOnReadyRef = useRef(false)
  const [lightbox, setLightbox] = useState(false)
  const [videoError, setVideoError] = useState(false)
  const [videoReady, setVideoReady] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [armedVideoId, setArmedVideoId] = useState<string | null>(null)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)

  const videoArmed = armedVideoId === hit.video_id

  const keyframe = frames.find((frame) => frame.is_keyframe)
  const active = frames[Math.min(activeIndex, frames.length - 1)] ?? frames[0]
  const offsetMs = active.ts_ms - (keyframe?.ts_ms ?? active.ts_ms)
  const offsetLabel =
    offsetMs === 0 ? 'keyframe' : `${offsetMs > 0 ? '+' : ''}${offsetMs} ms`
  const objects = [...hit.evidence.objects].sort(
    (left, right) =>
      (hit.evidence.object_counts[right] ?? 0) -
      (hit.evidence.object_counts[left] ?? 0),
  )

  function requestPlay() {
    if (!videoArmed) {
      playOnReadyRef.current = true
      setArmedVideoId(hit.video_id)
      return
    }
    const video = videoRef.current
    if (!video) {
      playOnReadyRef.current = true
      return
    }
    if (video.paused) {
      playOnReadyRef.current = true
      void video.play().catch(() => setPlaying(false))
    } else {
      video.pause()
    }
  }

  useImperativeHandle(ref, () => ({ togglePlay: requestPlay }))

  const seekToActive = useCallback((video: HTMLVideoElement) => {
    const target = active.ts_ms / 1000
    try {
      const limit = Number.isFinite(video.duration)
        ? Math.max(0, video.duration - 0.05)
        : target
      video.currentTime = Math.min(target, limit)
    } catch {
      // Metadata is not ready; loadedmetadata retries.
    }
  }, [active.ts_ms])

  useEffect(() => {
    setVideoError(false)
    setVideoReady(false)
    setPlaying(false)
    setDuration(0)
    setCurrentTime(0)
    setArmedVideoId(null)
    playOnReadyRef.current = false
  }, [hit.video_id])

  useEffect(() => {
    setVideoReady(false)
  }, [hit.video_id, active.ts_ms])

  useEffect(() => {
    setCurrentTime(active.ts_ms / 1000)
  }, [active.ts_ms])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const seek = () => seekToActive(video)
    if (video.readyState >= 1) seek()
    else video.addEventListener('loadedmetadata', seek, { once: true })
    return () => video.removeEventListener('loadedmetadata', seek)
  }, [hit.video_id, active.ts_ms, seekToActive])

  useEffect(() => {
    const target = document.querySelector(`[data-frame-index="${activeIndex}"]`)
    target?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [activeIndex, hit.video_id])

  function seekTo(value: number) {
    const video = videoRef.current
    if (!video) return
    video.currentTime = value
    setCurrentTime(value)
  }

  return (
    <section aria-label="Frame đang chọn" className="min-h-0">
      <div className="flex items-center justify-between gap-2 pb-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-mono text-sm font-semibold text-slate-900">
            {hit.video_id}
          </span>
          <span className="shrink-0 font-mono text-[11px] text-slate-600 tabular-nums">
            {formatMs(active.ts_ms)}
          </span>
          <span className="shrink-0 text-[11px] text-slate-500">{offsetLabel}</span>
          <span className="shrink-0 text-[11px] text-slate-500">shot {hit.shot_idx}</span>
          {hit.is_boilerplate && (
            <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
              intro/logo
            </span>
          )}
          {objects.length > 0 && (
            <span className="hidden min-w-0 items-center gap-1 md:flex">
              {objects.slice(0, 3).map((label) => (
                <span
                  key={label}
                  className="truncate rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600"
                  title={objects.map((item) => objectLabel(hit, item)).join(', ')}
                >
                  {objectLabel(hit, label)}
                </span>
              ))}
              {objects.length > 3 && (
                <span className="text-[10px] text-slate-500">+{objects.length - 3}</span>
              )}
            </span>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={requestPlay}
            aria-label={playing ? 'Tạm dừng video' : 'Phát video'}
            title={`${playing ? 'Tạm dừng' : 'Phát'} video (Space)`}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
          >
            <Icon name={playing ? 'pause' : 'play'} className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onSimilar}
            aria-label="Tìm frame tương tự"
            title="Tìm frame tương tự (R)"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
          >
            <Icon name="similar" className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onTimeline}
            aria-label="Xem keyframe lân cận"
            title="Xem keyframe lân cận (T)"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
          >
            <Icon name="timeline" className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setLightbox(true)}
            aria-label="Phóng to frame"
            title="Phóng to frame"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60"
          >
            <Icon name="expand" className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div
        className={`relative aspect-video ${
          compact ? 'max-h-[calc(100dvh-30rem)]' : 'max-h-[calc(100dvh-26rem)]'
        } w-full overflow-hidden rounded-xl border border-slate-200 bg-slate-950`}
        onDoubleClick={() => setLightbox(true)}
      >
        <img
          src={active.url}
          alt={`${hit.video_id} tại ${formatMs(active.ts_ms)}`}
          className="absolute inset-0 h-full w-full object-contain"
          draggable={false}
        />

        {videoArmed && !videoError && (
          <video
            key={hit.video_id}
            ref={videoRef}
            src={`/api/videos/${encodeURIComponent(hit.video_id)}/stream`}
            className={`absolute inset-0 h-full w-full object-contain transition-opacity duration-150 ${
              videoReady ? 'opacity-100' : 'opacity-0'
            }`}
            muted
            playsInline
            preload="metadata"
            aria-label={`Video ${hit.video_id} tại ${formatMs(active.ts_ms)}`}
            onLoadedMetadata={(event) => {
              const video = event.currentTarget
              setDuration(video.duration || 0)
              seekToActive(video)
              if (playOnReadyRef.current) {
                playOnReadyRef.current = false
                void video.play().catch(() => setPlaying(false))
              }
            }}
            onLoadedData={() => setVideoReady(true)}
            onSeeked={() => setVideoReady(true)}
            onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onError={() => {
              setVideoError(true)
              setVideoReady(false)
              setPlaying(false)
            }}
          />
        )}
      </div>

      {!videoArmed ? (
        <div className="mt-2 flex items-center justify-between gap-2 text-[10px] text-slate-500">
          <span>Video tải khi phát · Space</span>
          <span className="font-mono tabular-nums">{formatMs(active.ts_ms)}</span>
        </div>
      ) : (
        <div className="mt-2 flex items-center gap-2">
          <span className="w-14 shrink-0 font-mono text-[10px] text-slate-500 tabular-nums">
            {formatMs(Math.round(currentTime * 1000))}
          </span>
          <input
            type="range"
            min={0}
            max={duration || 0}
            step={0.05}
            value={Math.min(currentTime, duration || 0)}
            onChange={(event) => seekTo(Number(event.target.value))}
            disabled={!duration}
            aria-label="Tua video"
            className="h-1 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-blue-600 disabled:cursor-default"
          />
          <span className="w-14 shrink-0 text-right font-mono text-[10px] text-slate-500 tabular-nums">
            {duration ? formatMs(Math.round(duration * 1000)) : '--:--'}
          </span>
        </div>
      )}

      <div className="mt-2 space-y-1.5">
        <div className="flex items-center justify-between text-[10px] text-slate-500">
          <span>{frames.length} frame</span>
          <span className="font-mono tabular-nums">
            {Math.min(activeIndex + 1, frames.length)}/{frames.length}
          </span>
        </div>
        <div className="scroll-slim flex gap-1.5 overflow-x-auto pb-1">
          {frames.map((frame, index) => (
            <button
              key={`${frame.ts_ms}-${index}`}
              type="button"
              data-frame-index={index}
              onClick={() => onSelectFrame(index)}
              aria-pressed={index === activeIndex}
              title={`${formatMs(frame.ts_ms)}${frame.is_keyframe ? ' · keyframe' : ' · follow frame'}`}
              className={`relative w-24 shrink-0 overflow-hidden rounded-lg border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 focus-visible:ring-offset-[#f7f7f5] ${
                index === activeIndex
                  ? 'border-blue-600 ring-2 ring-blue-600/20'
                  : 'border-slate-200 hover:border-slate-400'
              }`}
            >
              <img
                src={frame.url}
                alt=""
                loading="lazy"
                decoding="async"
                className="aspect-video w-full object-cover"
              />
              <span className="absolute inset-x-0 bottom-0 bg-slate-950/80 py-0.5 text-center font-mono text-[9px] text-white tabular-nums">
                {formatMs(frame.ts_ms)}
              </span>
              {frame.is_keyframe && (
                <span className="absolute left-1 top-1 rounded bg-blue-600 px-1 text-[8px] font-bold text-white">
                  K
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {videoError && (
        <p className="mt-2 text-[11px] text-amber-700">
          Không stream được video. Ảnh keyframe vẫn dùng được.
        </p>
      )}

      {lightbox && (
        <ImageLightbox
          src={active.url}
          caption={`${hit.video_id} · ${formatMs(active.ts_ms)}${active.is_keyframe ? ' · keyframe' : ' · follow frame'}`}
          onClose={() => setLightbox(false)}
        />
      )}
    </section>
  )
})
