import { humanize } from '../contract'
import { GateBadge } from './GateBadge'

export interface WorkflowDefinition {
  initial: string
  states: Record<string, { terminal?: boolean; enter_jobs?: unknown[]; on?: Record<string, { to: string; gate?: string; gate_if?: string }> }>
}
export interface Transition { event: string; from_state: string; to_state: string; outcome: string; created_at?: string }
export interface InstanceView { state: string; status: string }

/** States in the order the 'advance' path visits them. */
export function orderedStates(def: WorkflowDefinition): string[] {
  const out: string[] = []
  let cur: string | undefined = def.initial
  while (cur && !out.includes(cur)) {
    out.push(cur)
    cur = def.states[cur]?.on?.advance?.to
  }
  return out
}

/** A pass-through state has no jobs and no gate. It exists so the audit trail shows the step happened. */
export function isPassThrough(def: WorkflowDefinition, name: string): boolean {
  const s = def.states[name]
  if (!s || name === def.initial || s.terminal) return false
  return !s.enter_jobs?.length && !Object.values(s.on ?? {}).some((e) => e.gate)
}

export function WorkflowTimeline({ definition, instance, transitions }: { definition: WorkflowDefinition; instance: InstanceView; transitions: Transition[] }) {
  const order = orderedStates(definition)
  const currentIdx = order.indexOf(instance.state)
  const finished = instance.status === 'completed'
  return (
    <ol className="timeline" aria-label="Workflow steps">
      {order.map((name, i) => {
        const done = finished || i < currentIdx
        const current = !finished && i === currentIdx
        const waiting = current && instance.status === 'waiting_gate'
        const gateId = definition.states[name]?.on?.advance?.gate
        const cls = done ? 'tl-done' : waiting ? 'tl-waiting' : current ? 'tl-current' : ''
        const state = done ? 'done' : waiting ? 'paused at a gate' : current ? 'in progress' : 'not reached'
        const entered = transitions.find((t) => t.to_state === name)
        return (
          <li key={name} className={`tl-item ${cls}`} aria-current={current ? 'step' : undefined}>
            <span className="tl-dot" aria-hidden="true">{done ? '✓' : ''}</span>
            <div>
              <div className="tl-title">{humanize(name)} <span className="sr-only">, {state}</span></div>
              <div className="tl-meta">
                {done && isPassThrough(definition, name) ? 'Recorded for the audit trail' : waiting ? 'Waiting on a person to approve' : state}
                {entered?.created_at && done ? ` · ${new Date(entered.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}` : ''}
              </div>
              {gateId && (done || current) && <div style={{ marginTop: 6 }}><GateBadge gateId={gateId} status={waiting ? 'waiting' : done ? 'approved' : undefined} /></div>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
