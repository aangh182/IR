import type { ReactNode } from 'react'

export type IconName =
  | 'search'
  | 'filter'
  | 'play'
  | 'pause'
  | 'expand'
  | 'copy'
  | 'similar'
  | 'timeline'
  | 'check'
  | 'close'
  | 'keyboard'
  | 'back'
  | 'video'
  | 'image'
  | 'alert'
  | 'tag'
  | 'more'

const paths: Record<IconName, ReactNode> = {
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.6-3.6" />
    </>
  ),
  filter: (
    <>
      <path d="M4 7h16M4 17h16" />
      <circle cx="9" cy="7" r="2.1" />
      <circle cx="15" cy="17" r="2.1" />
    </>
  ),
  play: <path d="M8 5.4v13.2L18.4 12z" fill="currentColor" stroke="none" />,
  pause: (
    <>
      <path d="M9 5v14M15 5v14" strokeWidth="2.6" />
    </>
  ),
  expand: <path d="M9.5 4.5h-5v5M14.5 4.5h5v5M9.5 19.5h-5v-5M14.5 19.5h5v-5" />,
  copy: (
    <>
      <rect x="8" y="8" width="11" height="11" rx="2" />
      <path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" />
    </>
  ),
  similar: (
    <>
      <rect x="3" y="3" width="12" height="12" rx="2" />
      <path d="M9 21h10a2 2 0 0 0 2-2V9" />
      <path d="m15.5 15.5 4 4" />
    </>
  ),
  timeline: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M7 5v14M17 5v14M3 12h18" />
    </>
  ),
  check: <path d="m5 12.5 4.2 4.2L19 6.5" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  keyboard: (
    <>
      <rect x="2.5" y="6" width="19" height="12" rx="2" />
      <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7.5 14h9" />
    </>
  ),
  back: <path d="M14.5 18.5 8 12l6.5-6.5" />,
  video: (
    <>
      <rect x="3" y="5" width="13" height="14" rx="2" />
      <path d="m16 10 5-3v10l-5-3z" />
    </>
  ),
  image: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="10" r="1.4" />
      <path d="m4 18 5-5 4 4 3-3 4 4" />
    </>
  ),
  alert: (
    <>
      <path d="M12 4 2.9 20h18.2z" />
      <path d="M12 9v5M12 17h.01" />
    </>
  ),
  tag: (
    <>
      <path d="M20.6 13.6 12 22l-9-9V3h10l7.6 7.6a2 2 0 0 1 0 3z" />
      <circle cx="7.5" cy="7.5" r="1.4" />
    </>
  ),
  more: (
    <>
      <circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="19" cy="12" r="1.4" fill="currentColor" stroke="none" />
    </>
  ),
}

export function Icon({
  name,
  className = 'h-4 w-4',
}: {
  name: IconName
  className?: string
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {paths[name]}
    </svg>
  )
}
