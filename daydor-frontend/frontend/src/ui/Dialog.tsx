import { useEffect, useRef, type ReactNode } from 'react'
import { Button } from './Button'

/** A modal dialog. Escape or the close button dismisses it; focus starts on the close button and
 *  tabbing stays inside while it is open. */
export function Dialog({ open, title, onClose, children, width = 560 }: { open: boolean; title: string; onClose: () => void; children: ReactNode; width?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key !== 'Tab' || !ref.current) return
      const items = ref.current.querySelectorAll<HTMLElement>('button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')
      if (items.length === 0) return
      const first = items[0]!, last = items[items.length - 1]!
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); previous?.focus?.() }
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="drawer-backdrop" style={{ alignItems: 'center', justifyContent: 'center', padding: 16 }} onClick={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title} className="panel" style={{ width: `min(${width}px, 100%)`, maxHeight: '92vh', overflow: 'auto' }} onClick={(e) => e.stopPropagation()}>
        <div className="spread" style={{ marginBottom: 14 }}><h2>{title}</h2><Button ref={closeRef} variant="quiet" onClick={onClose}>Close</Button></div>
        {children}
      </div>
    </div>
  )
}
