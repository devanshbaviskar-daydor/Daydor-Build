import { Badge } from './Badge'

/** Shown wherever a value comes from a fake vendor connection instead of a real one. */
export function MockAdapterBadge({ vendor }: { vendor: string }) {
  return <Badge tone="outline" title={`${vendor} is a stand-in for now. Nothing was sent to a real provider.`}>Test {vendor}</Badge>
}

/** Shown on soft-gate (Jev) results: recorded for review, never applied. */
export function ShadowModeBadge() {
  return <Badge tone="outline" title="Jev's answer is recorded for comparison only. A person's decision is what counts.">Shadow mode, not applied</Badge>
}
