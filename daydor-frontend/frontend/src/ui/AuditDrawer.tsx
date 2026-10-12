import { useEffect, useRef, type ReactNode } from 'react'
import { Button } from './Button'

export interface AuditEntry { id: string; at: string; actor: string; action: string }

/** A side panel for the audit trail of one record. Escape and the close button both dismiss it. */
export function AuditDrawer({ open, title, entries, onClose, children, emptyText = 'Nothing has been recorded for this yet.' }: {
  open: boolean; title: string; entries: AuditEntry[]; onClose: () => void; children?: ReactNode
  /** Pass null while loading so the empty message does not flash. */
  emptyText?: string | null
}) {
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="spread"><h2>{title}</h2><Button ref={closeRef} variant="quiet" onClick={onClose}>Close</Button></div>
        {children}
        {entries.length === 0 ? (emptyText === null ? null : <p className="muted">{emptyText}</p>) : (
          <ul className="list" style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {entries.map((e) => (
              <li key={e.id} className="list-row" style={{ display: 'block' }}>
                <div>{e.action}</div>
                <div className="muted" style={{ fontSize: 13 }}>{e.actor} · {new Date(e.at).toLocaleString('en-IN')}</div>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  )
}
