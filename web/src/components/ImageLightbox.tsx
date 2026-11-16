import { useEffect } from 'react'
import { createPortal } from 'react-dom'

type Props = {
  src: string
  caption?: string
  onClose: () => void
}

export function ImageLightbox({ src, caption, onClose }: Props) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [onClose])

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={caption ? `Xem ảnh ${caption}` : 'Xem ảnh'}
      onClick={onClose}
      className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/90 p-4 backdrop-blur-sm"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Đóng"
        autoFocus
        className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-lg text-white transition hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
      >
        ✕
      </button>
      <figure
        onClick={(event) => event.stopPropagation()}
        className="lightbox-figure flex max-h-full max-w-full flex-col items-center"
      >
        <img
          src={src}
          alt={caption ?? ''}
          className="max-h-[88vh] w-auto max-w-[92vw] rounded-lg object-contain shadow-2xl shadow-black/60"
        />
        {caption && (
          <figcaption className="mt-3 font-mono text-xs text-slate-300">{caption}</figcaption>
        )}
      </figure>
    </div>,
    document.body,
  )
}
