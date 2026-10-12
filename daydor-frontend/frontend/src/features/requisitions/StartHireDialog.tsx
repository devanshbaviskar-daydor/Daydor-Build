import { useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLookups, useStartHire } from '../../api/hooks'
import { explain } from '../../api/errors'
import type { StartHireBody } from '../../api/types'
import { labelFor } from '../../contract'
import { Button, Dialog } from '../../ui'

type Row = Record<string, unknown>

/** Opens a requisition for one open seat. The backend's hire flow reads the interviewer, interview time,
 *  comp band and proposed base from this same request (a Sprint 2 simplification), so they are asked for here.
 *  It also reads the new hire's own personal and payroll-setup details this same way, once the flow reaches
 *  employee creation (step 10) and payroll profile (step 18) -- there is no later checkpoint to patch them
 *  in, so they are collected up front too (see docs/integration-notes.md, finding 6). A real system would
 *  collect these at offer acceptance; this prototype has no such step. */
export function StartHireDialog({ position, title, onClose }: { position: Row; title: string; onClose: () => void }) {
  const nav = useNavigate()
  const { lookups } = useLookups(['employee', 'comp_band', 'location', 'retention_policy'])
  const start = useStartHire()
  const bands = useMemo(() => Object.values(lookups.comp_band ?? {}).filter((b) => b.job_profile_id === position.job_profile_id), [lookups.comp_band, position.job_profile_id])
  const people = Object.values(lookups.employee ?? {})
  const locations = Object.values(lookups.location ?? {})
  const retentionPolicies = Object.values(lookups.retention_policy ?? {})
  const [v, setV] = useState({
    manager: '', start: '', channel: 'company_site', min: '', max: '', interviewer: '', when: '', band: '', base: '', equity: '',
    location: '', employmentType: 'full_time', dob: '', address: '', aadhaarLast4: '', basicDa: '', taxRegime: 'new',
    payFrequency: 'monthly', paymentMethod: 'bank_transfer', uan: '',
  })
  const [errs, setErrs] = useState<Record<string, string>>({})
  const [key] = useState(() => crypto.randomUUID())
  const set = (k: keyof typeof v, val: string) => setV((x) => ({ ...x, [k]: val }))
  const location = lookups.location?.[v.location]
  const country = location?.country_code as string | undefined

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const bad: Record<string, string> = {}
    if (!v.manager) bad.manager = 'Choose the hiring manager'
    if (!v.start) bad.start = 'Choose a target start date'
    if (!v.min || !v.max) bad.range = 'Enter the pay range'
    else if (Number(v.min) > Number(v.max)) bad.range = 'The minimum cannot be above the maximum'
    if (!v.when) bad.when = 'Choose the interview time'
    if (!v.band) bad.band = 'Choose the comp band'
    if (!v.base || Number(v.base) <= 0) bad.base = 'Enter the proposed base pay'
    if (!v.location) bad.location = 'Choose where this person will work'
    if (!v.dob) bad.dob = "Enter the new hire's date of birth"
    if (!v.address) bad.address = 'Enter a personal address'
    if (!v.aadhaarLast4) bad.aadhaarLast4 = 'Required by the backend for every hire, not only in India (a known gap)'
    if (!v.basicDa || Number(v.basicDa) <= 0) bad.basicDa = 'Enter the monthly basic plus dearness allowance'
    if (retentionPolicies.length && !retentionPolicies[0]) bad.retention = 'No document retention policy exists yet'
    setErrs(bad)
    if (Object.keys(bad).length) return
    const body: StartHireBody = {
      position_id: String(position.id), hiring_manager_id: v.manager, target_start_date: v.start, channel: v.channel || 'company_site',
      pay_range_min: Number(v.min), pay_range_max: Number(v.max), interviewer_employee_id: v.interviewer || v.manager,
      scheduled_at: new Date(v.when).toISOString(), comp_band_id: v.band, proposed_base: Number(v.base), ...(v.equity ? { proposed_equity: Number(v.equity) } : {}),
      legal_entity_id: String(location?.legal_entity_id ?? ''), location_id: v.location, state_code: String(location?.state_code ?? ''),
      employment_type: v.employmentType, date_of_birth: v.dob, personal_address: v.address, aadhaar_last4: v.aadhaarLast4,
      basic_da_monthly: Number(v.basicDa), tax_regime_election: v.taxRegime,
      retention_class_id: retentionPolicies[0] ? String(retentionPolicies[0].id) : undefined,
      pay_frequency: v.payFrequency, payment_method: v.paymentMethod,
      work_state: String(location?.state_code ?? ''), tax_state: String(location?.state_code ?? ''),
      ...(country === 'IN' && v.uan ? { uan_number: v.uan } : {}),
    }
    start.mutate({ body, key }, { onSuccess: (r) => { onClose(); nav(`/requisitions/${r.requisition_id}`, { state: { notice: r.existing ? 'A hire was already in progress for this position, so this is that one.' : 'Requisition opened. It now waits for the founder to approve the budget.' } }) } })
  }
  const field = (id: string, label: string, widget: React.ReactNode, help?: string) => (
    <div><label className="label" htmlFor={id}>{label}</label>{widget}{(errs[id] || help) && <p className="help" style={errs[id] ? { color: 'var(--danger)' } : undefined}>{errs[id] ?? help}</p>}</div>
  )
  return (
    <Dialog open title={`Start hiring: ${title}`} onClose={onClose} width={640}>
      <form onSubmit={submit} noValidate className="stack">
        {field('manager', 'Hiring manager', <select id="manager" className="input" value={v.manager} onChange={(e) => set('manager', e.target.value)}><option value="">Choose…</option>{people.map((p) => <option key={String(p.id)} value={String(p.id)}>{labelFor('employee', p)}</option>)}</select>)}
        {field('start', 'Target start date', <input id="start" className="input" type="date" value={v.start} onChange={(e) => set('start', e.target.value)} />)}
        {field('channel', 'Where to post it', <input id="channel" className="input" value={v.channel} onChange={(e) => set('channel', e.target.value)} />, 'Free text for now: the model does not list the channels yet.')}
        <div className="row" style={{ alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 180px' }}><label className="label" htmlFor="min">Pay range from (₹ a year)</label><input id="min" className="input" type="number" value={v.min} onChange={(e) => set('min', e.target.value)} /></div>
          <div style={{ flex: '1 1 180px' }}><label className="label" htmlFor="max">to (₹ a year)</label><input id="max" className="input" type="number" value={v.max} onChange={(e) => set('max', e.target.value)} /></div>
        </div>
        {errs.range && <p className="help" style={{ color: 'var(--danger)' }}>{errs.range}</p>}
        <p className="muted" style={{ fontSize: 14 }}>The hiring flow reads the next four answers from this request, so they are needed now even though the interview and offer come later.</p>
        {field('interviewer', 'Interviewer', <select id="interviewer" className="input" value={v.interviewer} onChange={(e) => set('interviewer', e.target.value)}><option value="">Same as the hiring manager</option>{people.map((p) => <option key={String(p.id)} value={String(p.id)}>{labelFor('employee', p)}</option>)}</select>)}
        {field('when', 'Interview time', <input id="when" className="input" type="datetime-local" value={v.when} onChange={(e) => set('when', e.target.value)} />)}
        {field('band', 'Comp band for the offer', <select id="band" className="input" value={v.band} onChange={(e) => set('band', e.target.value)}><option value="">{bands.length ? 'Choose…' : 'No comp band for this job profile'}</option>{bands.map((b) => <option key={String(b.id)} value={String(b.id)}>{labelFor('comp_band', b)}</option>)}</select>)}
        {field('base', 'Proposed base pay (₹ a year)', <input id="base" className="input" type="number" value={v.base} onChange={(e) => set('base', e.target.value)} />, 'An offer outside the band goes to the founder for approval.')}
        {field('equity', 'Proposed equity (optional)', <input id="equity" className="input" type="number" value={v.equity} onChange={(e) => set('equity', e.target.value)} />)}
        <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '4px 0' }} />
        <p className="muted" style={{ fontSize: 14 }}>The flow also reads the new hire's own details here, once it creates their employee and payroll-profile records -- there is no later point to add them (a known simplification; a real system would collect these at offer acceptance).</p>
        {field('location', 'Work location', <select id="location" className="input" value={v.location} onChange={(e) => set('location', e.target.value)}><option value="">{locations.length ? 'Choose…' : 'No locations set up yet'}</option>{locations.map((l) => <option key={String(l.id)} value={String(l.id)}>{String(l.name)}</option>)}</select>)}
        {field('employmentType', 'Employment type', <input id="employmentType" className="input" value={v.employmentType} onChange={(e) => set('employmentType', e.target.value)} />, 'Free text for now: the model does not list the values yet.')}
        {field('dob', "New hire's date of birth", <input id="dob" className="input" type="date" value={v.dob} onChange={(e) => set('dob', e.target.value)} />)}
        {field('address', 'Personal address', <input id="address" className="input" value={v.address} onChange={(e) => set('address', e.target.value)} />)}
        {field('aadhaarLast4', 'Aadhaar, last 4 digits', <input id="aadhaarLast4" className="input" maxLength={4} value={v.aadhaarLast4} onChange={(e) => set('aadhaarLast4', e.target.value)} />)}
        <div className="row" style={{ alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 180px' }}>{field('basicDa', 'Basic + DA, per month (₹)', <input id="basicDa" className="input" type="number" value={v.basicDa} onChange={(e) => set('basicDa', e.target.value)} />)}</div>
          <div style={{ flex: '1 1 180px' }}>{field('taxRegime', 'Tax regime election', <input id="taxRegime" className="input" value={v.taxRegime} onChange={(e) => set('taxRegime', e.target.value)} />)}</div>
        </div>
        <div className="row" style={{ alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 180px' }}>{field('payFrequency', 'Pay frequency', <input id="payFrequency" className="input" value={v.payFrequency} onChange={(e) => set('payFrequency', e.target.value)} />)}</div>
          <div style={{ flex: '1 1 180px' }}>{field('paymentMethod', 'Payment method', <input id="paymentMethod" className="input" value={v.paymentMethod} onChange={(e) => set('paymentMethod', e.target.value)} />)}</div>
        </div>
        {country === 'IN' && field('uan', 'UAN (optional)', <input id="uan" className="input" value={v.uan} onChange={(e) => set('uan', e.target.value)} />)}
        {errs.retention && <p className="notice notice-danger">{errs.retention}</p>}
        {start.isError && <p role="alert" className="notice notice-danger">{explain(start.error)}</p>}
        <div className="row"><Button type="submit" variant="primary" busy={start.isPending}>Open requisition</Button><Button onClick={onClose}>Cancel</Button></div>
      </form>
    </Dialog>
  )
}
