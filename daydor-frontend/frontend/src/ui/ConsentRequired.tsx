export type ConsentState = 'missing' | 'withdrawn'

const TEXT: Record<ConsentState, string> = {
  missing: 'Not collected until the employee gives consent.',
  withdrawn: 'Consent was withdrawn, so this value is not available.',
}

export function ConsentRequired({ state = 'missing' }: { state?: ConsentState }) {
  return <span role="note" className="restricted" data-consent={state}>{TEXT[state]}</span>
}
