import type { ReactNode } from 'react'

export type Tone = 'neutral' | 'accent' | 'ok' | 'warn' | 'danger' | 'outline'
const MARKS: Record<Tone, string | undefined> = { neutral: undefined, accent: undefined, ok: '✓', warn: '◔', danger: '✕', outline: undefined }

export function Badge({ tone = 'neutral', mark, title, children }: { tone?: Tone; mark?: string; title?: string; children: ReactNode }) {
  return (
    <span className={`badge badge-${tone}`} data-mark={mark ?? MARKS[tone]} title={title}>
      {children}
    </span>
  )
}
