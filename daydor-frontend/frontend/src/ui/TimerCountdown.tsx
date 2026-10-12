import { Badge } from './Badge'

/** Plain wording for time left. Whole days, local time; business-day rules stay with the backend. */
export function describeRemaining(dueAt: string | Date, now: Date = new Date()): { text: string; tone: 'ok' | 'warn' | 'danger' } {
  const ms = new Date(dueAt).getTime() - now.getTime()
  const day = 86_400_000
  if (ms < 0) {
    const d = Math.max(1, Math.ceil(-ms / day))
    return { text: `Overdue by ${d} ${d === 1 ? 'day' : 'days'}`, tone: 'danger' }
  }
  const hours = Math.floor(ms / 3_600_000)
  if (hours < 24) return { text: hours <= 1 ? 'Due within the hour' : `${hours} hours left`, tone: 'warn' }
  const d = Math.floor(ms / day)
  return { text: `${d} ${d === 1 ? 'day' : 'days'} left`, tone: d <= 3 ? 'warn' : 'ok' }
}

export function TimerCountdown({ dueAt, now, label }: { dueAt: string; now?: Date; label?: string }) {
  const r = describeRemaining(dueAt, now)
  return <Badge tone={r.tone} title={`Due ${new Date(dueAt).toLocaleString('en-IN')}`}>{label ? `${label}: ` : ''}{r.text}</Badge>
}
