import { useState } from 'react'
import { useAuditTrail } from '../../api/hooks'
import { explain } from '../../api/errors'
import { AuditDrawer, Button } from '../../ui'

/** Opens the audit trail for one record. The list is fetched only when the drawer opens. */
export function AuditTrailButton({ table, id, title = 'Audit trail' }: { table: string; id: string; title?: string }) {
  const [open, setOpen] = useState(false)
  const q = useAuditTrail(table, id, open)
  return (
    <>
      <Button onClick={() => setOpen(true)}>View audit trail</Button>
      <AuditDrawer open={open} title={title} onClose={() => setOpen(false)} emptyText={q.data ? undefined : null}
        entries={(q.data?.entries ?? []).map((e) => ({ id: e.id, at: e.at, actor: e.actor, action: e.action }))}>
        {q.isPending && <p aria-live="polite">Loading…</p>}
        {q.isError && <p role="alert" className="notice notice-danger">{explain(q.error)}</p>}
        {q.data && !q.data.sources.workflow && <p className="muted" style={{ fontSize: 14 }}>Your role cannot see workflow steps, so they are not listed here.</p>}
      </AuditDrawer>
    </>
  )
}
