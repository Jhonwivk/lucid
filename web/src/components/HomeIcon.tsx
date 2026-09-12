import type { CSSProperties, ReactNode } from 'react'

export type HomeIconName = 'database' | 'calendar' | 'leaf' | 'file' | 'grid' | 'list' | 'search' | 'chevron' | 'arrow' | 'plus' | 'more' | 'clock' | 'check' | 'insight' | 'pin' | 'bolt' | 'book' | 'play' | 'refresh' | 'close'

const paths: Record<HomeIconName, ReactNode> = {
  database: <><ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v7c0 4 14 4 14 0V5M5 12v7c0 4 14 4 14 0v-7"/></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6M17 2v6M3 11h18"/></>,
  leaf: <><path d="M20 3c1 10-1 16-8 17-7 1-10-6-6-10 3-3 8-1 14-7Z"/><path d="M3 22 15 10"/></>,
  file: <><path d="M14 2H5v20h14V7zM14 2v6h5M8 12h7M8 16h5"/></>,
  grid: <><rect x="3" y="3" width="6" height="6" rx=".5"/><rect x="15" y="3" width="6" height="6" rx=".5"/><rect x="3" y="15" width="6" height="6" rx=".5"/><rect x="15" y="15" width="6" height="6" rx=".5"/></>,
  list: <path d="M8 5h13M8 12h13M8 19h13M3 5h.01M3 12h.01M3 19h.01"/>,
  search: <><circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/></>,
  chevron: <path d="m8 10 4 4 4-4"/>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>,
  plus: <path d="M12 4v16M4 12h16"/>,
  more: <><circle cx="4" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="20" cy="12" r="1"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  insight: <><circle cx="12" cy="12" r="9"/><path d="m4 15 4-3 3 2 3-8 2 10 4-2"/></>,
  pin: <><path d="M19 9c0 5-7 12-7 12S5 14 5 9a7 7 0 0 1 14 0Z"/><circle cx="12" cy="9" r="2"/></>,
  bolt: <path d="m13 2-9 12h7l-1 8 10-13h-7z"/>,
  book: <><path d="M12 5c-3-3-7-2-10-1v16c4-2 7-1 10 1 3-2 6-3 10-1V4c-4-1-7-2-10 1ZM12 5v16"/></>,
  play: <path d="m8 4 12 8-12 8Z"/>,
  refresh: <><path d="M20 8a9 9 0 1 0 1 8M20 2v6h-6"/></>,
  close: <path d="m6 6 12 12M6 18 18 6"/>,
}

export function HomeIcon({ name, size = 20, style }: { name: HomeIconName; size?: number; style?: CSSProperties }) {
  return <svg className="lu-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}>{paths[name]}</svg>
}
