import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import { renderApp, signInAs } from '../test/utils'

let current: ReturnType<typeof renderApp> | null = null
async function visit(name: string, path: string) {
  current?.unmount(); localStorage.clear()
  current = renderApp(path)
  await signInAs(name)
  return current
}
const pendingCard = async (gate: string) => (await screen.findAllByRole('article')).find((a) => within(a).queryByText(gate) && within(a).queryByText('Waiting for approval') && within(a).queryByRole('button', { name: 'Approve' }))!
async function approve(name: string, gate: string) {
  await visit(name, '/approvals')
  const card = await pendingCard(gate)
  await userEvent.click(within(card).getByRole('button', { name: 'Approve' }))
  await waitFor(() => expect(within(card).queryByRole('button', { name: 'Approve' })).toBeNull())
}
async function startHireOnSecondSeat(base: string) {
  await visit('Kavya Menon', '/positions')
  const buttons = await screen.findAllByRole('button', { name: /Start hiring for Backend Engineer, Engineering/ })
  await userEvent.click(buttons[1]!)           // pos-2: pos-1 already has a hire
  const dialog = await screen.findByRole('dialog', { name: /Start hiring/ })
  await userEvent.selectOptions(within(dialog).getByLabelText('Hiring manager'), 'e-meera')
  fireEvent.change(within(dialog).getByLabelText('Target start date'), { target: { value: '2026-12-15' } })
  await userEvent.type(within(dialog).getByLabelText('Pay range from (₹ a year)'), '1800000')
  await userEvent.type(within(dialog).getByLabelText('to (₹ a year)'), '3000000')
  fireEvent.change(within(dialog).getByLabelText('Interview time'), { target: { value: '2026-11-20T10:00' } })
  await userEvent.selectOptions(within(dialog).getByLabelText('Comp band for the offer'), 'cb-1')
  await userEvent.type(within(dialog).getByLabelText('Proposed base pay (₹ a year)'), base)
  await fillNewHireDetails(dialog)
  await userEvent.click(within(dialog).getByRole('button', { name: 'Open requisition' }))
  await screen.findByText('Requisition opened. It now waits for the founder to approve the budget.')
}
async function fillNewHireDetails(dialog: HTMLElement) {
  await userEvent.selectOptions(within(dialog).getByLabelText('Work location'), 'loc-blr')
  fireEvent.change(within(dialog).getByLabelText("New hire's date of birth"), { target: { value: '1995-04-12' } })
  await userEvent.type(within(dialog).getByLabelText('Personal address'), '1 MG Road, Bengaluru')
  await userEvent.type(within(dialog).getByLabelText('Aadhaar, last 4 digits'), '1234')
  await userEvent.type(within(dialog).getByLabelText('Basic + DA, per month (₹)'), '50000')
}

describe('positions', () => {
  it('lists open seats and filled positions with counts, and offers Start hiring only where it applies', async () => {
    await visit('Kavya Menon', '/positions')
    expect(await screen.findByRole('button', { name: 'Open seats (3)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Filled (2)' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Start hiring for/ })).toHaveLength(3)
    await userEvent.click(screen.getByRole('button', { name: 'Filled (2)' }))
    expect(await screen.findByText('Meera Iyer')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Start hiring for/ })).toBeNull()
  })

  it('creates a position from a form generated from the contract', async () => {
    await visit('Kavya Menon', '/positions')
    await userEvent.click(await screen.findByRole('button', { name: 'New position' }))
    const dialog = await screen.findByRole('dialog', { name: 'New position' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create position' }))
    expect(within(dialog).getAllByText('Required').length).toBeGreaterThan(2)
    await userEvent.selectOptions(within(dialog).getByLabelText(/^Department/), 'dept-sales')
    await userEvent.selectOptions(within(dialog).getByLabelText(/^Job profile/), 'jp-2')
    await userEvent.type(within(dialog).getByLabelText(/Full-time equivalent/), '1')
    await userEvent.type(within(dialog).getByLabelText(/Budget a year/), '1600000')
    fireEvent.change(within(dialog).getByLabelText(/^Opened at/), { target: { value: '2026-10-01' } })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create position' }))
    expect(await screen.findByRole('button', { name: 'Open seats (4)' })).toBeInTheDocument()
  })

  it('lets a manager open requisitions but not edit positions, and hides Positions from employees', async () => {
    await visit('Meera Iyer', '/positions')
    expect(await screen.findAllByRole('button', { name: /^Start hiring for/ })).toHaveLength(3)
    expect(screen.queryByRole('button', { name: 'New position' })).toBeNull()
    await visit('Arjun Rao', '/')
    expect(within(screen.getByRole('navigation', { name: 'Primary' })).queryByRole('link', { name: 'Positions' })).toBeNull()
  })

  it('checks the start-hiring form before sending it', async () => {
    await visit('Kavya Menon', '/positions')
    await userEvent.click((await screen.findAllByRole('button', { name: /^Start hiring for/ }))[1]!)
    const dialog = await screen.findByRole('dialog', { name: /Start hiring/ })
    await userEvent.type(within(dialog).getByLabelText('Pay range from (₹ a year)'), '3000000')
    await userEvent.type(within(dialog).getByLabelText('to (₹ a year)'), '1000000')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Open requisition' }))
    expect(within(dialog).getByText('Choose the hiring manager')).toBeInTheDocument()
    expect(within(dialog).getByText('The minimum cannot be above the maximum')).toBeInTheDocument()
    expect(within(dialog).getByText('Choose the interview time')).toBeInTheDocument()
    expect(within(dialog).getByText('Choose the comp band')).toBeInTheDocument()
  })
})

describe('requisitions', () => {
  it('shows a plain stage for each requisition', async () => {
    await visit('Kavya Menon', '/requisitions')
    const rows = (await screen.findAllByRole('row')).slice(1)
    expect(rows).toHaveLength(3)
    expect(within(rows.find((r) => within(r).queryByText('Waiting for budget approval'))!).getByText('Backend Engineer, Engineering')).toBeInTheDocument()
    expect(screen.getAllByText('Posted', { selector: '.badge' })).toHaveLength(2)
  })

  it('shows a requisition mid-hire with its screening, interview and an out-of-band offer', async () => {
    await visit('Kavya Menon', '/requisitions/req-3')
    const card = await screen.findByRole('article', { name: 'Candidate Rahul Verma' })
    expect(within(card).getByText(/Score/)).toHaveTextContent('81%')
    expect(within(card).getByText('Test screener')).toBeInTheDocument()
    expect(within(card).getByText(/it always needs HR sign-off/)).toBeInTheDocument()
    expect(within(card).getByText('₹28,00,000')).toBeInTheDocument()
    expect(within(card).getByText('Outside band')).toBeInTheDocument()
    expect(within(card).getByText(/₹12,00,000 to ₹20,00,000/)).toBeInTheDocument()
    expect(within(card).getByText('Background check')).toBeInTheDocument()
    expect(within(card).getByText(/Not started/)).toBeInTheDocument()
    expect(within(card).getAllByRole('link', { name: 'Open the approval' }).length).toBeGreaterThan(0)
  })

  it('shows a finished hire with its background check run by a test vendor', async () => {
    await visit('Kavya Menon', '/requisitions/req-4')
    const card = await screen.findByRole('article', { name: 'Candidate Isha Nair' })
    expect(await within(card).findByText('Test background check vendor')).toBeInTheDocument()
    expect(within(card).getByText(/No adverse findings/)).toBeInTheDocument()
    expect(within(card).getByText('Within band')).toBeInTheDocument()
  })

  it('explains what a hiring manager and payroll cannot see', async () => {
    await visit('Meera Iyer', '/requisitions/req-3')
    const card = await screen.findByRole('article', { name: 'Candidate' })
    expect(within(card).getByText('Candidate not visible to your role')).toBeInTheDocument()
    expect(within(card).getByText(/hides a candidate’s details from managers until they become an employee/)).toBeInTheDocument()
    await visit('Dev Patel', '/requisitions/req-3')
    expect(await screen.findByText('Your role cannot see candidates.')).toBeInTheDocument()
  })

  it('takes a hire from a new requisition to an approved offer', async () => {
    await startHireOnSecondSeat('2400000')
    expect(screen.getByText('Waiting for budget approval')).toBeInTheDocument()

    await approve('Rohan Mehta', 'Requisition budget sign-off')
    await visit('Kavya Menon', '/requisitions')
    await userEvent.click((await screen.findAllByRole('link', { name: /Backend Engineer, Engineering/ }))[0]!)
    expect(await screen.findByText('Posted')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Enter an application' }))
    const dialog = await screen.findByRole('dialog', { name: 'Enter an application' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Enter application' }))
    expect(within(dialog).getByText('Enter a valid email address')).toBeInTheDocument()
    await userEvent.type(within(dialog).getByLabelText('Full name'), 'Neha Gupta')
    await userEvent.type(within(dialog).getByLabelText('Email'), 'neha.gupta@example.test')
    await userEvent.type(within(dialog).getByLabelText('Phone'), '+91 98450 00000')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Enter application' }))
    const card = await screen.findByRole('article', { name: 'Candidate Neha Gupta' })
    expect(within(card).getByText('Needs a decision')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Enter an application' })).toBeNull()      // one candidate per hire

    await approve('Kavya Menon', 'AEDT notice and bias-audit currency')
    await visit('Kavya Menon', '/requisitions')
    await userEvent.click((await screen.findAllByRole('link', { name: /Backend Engineer, Engineering/ }))[0]!)
    const after = await screen.findByRole('article', { name: 'Candidate Neha Gupta' })
    expect(await within(after).findByText('Within band')).toBeInTheDocument()
    expect(within(after).getByText(/with Meera Iyer/)).toBeInTheDocument()
    expect(within(after).getByText('₹24,00,000')).toBeInTheDocument()
  })

  it('sends an out-of-band offer to the founder and clears it when approved', async () => {
    await startHireOnSecondSeat('4500000')
    await approve('Rohan Mehta', 'Requisition budget sign-off')
    await visit('Kavya Menon', '/requisitions')
    await userEvent.click((await screen.findAllByRole('link', { name: /Backend Engineer, Engineering/ }))[0]!)
    await userEvent.click(await screen.findByRole('button', { name: 'Enter an application' }))
    const dialog = await screen.findByRole('dialog', { name: 'Enter an application' })
    await userEvent.type(within(dialog).getByLabelText('Full name'), 'Karthik Rao')
    await userEvent.type(within(dialog).getByLabelText('Email'), 'karthik.rao@example.test')
    await userEvent.type(within(dialog).getByLabelText('Phone'), '+91 98450 12345')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Enter application' }))
    await screen.findByRole('article', { name: 'Candidate Karthik Rao' })

    await approve('Kavya Menon', 'AEDT notice and bias-audit currency')
    await visit('Kavya Menon', '/requisitions')
    await userEvent.click((await screen.findAllByRole('link', { name: /Backend Engineer, Engineering/ }))[0]!)
    const card = await screen.findByRole('article', { name: 'Candidate Karthik Rao' })
    expect(await within(card).findByText('Outside band')).toBeInTheDocument()
    expect(within(card).getByText(/needs the founder’s approval/)).toBeInTheDocument()

    await approve('Rohan Mehta', 'Offer or comp change outside band')
    await visit('Kavya Menon', '/requisitions')
    await userEvent.click((await screen.findAllByRole('link', { name: /Backend Engineer, Engineering/ }))[0]!)
    const done = await screen.findByRole('article', { name: 'Candidate Karthik Rao' })
    expect(within(done).getAllByText('Approved').length).toBeGreaterThan(0)
  })

  it('returns the existing hire when a position already has one', async () => {
    await visit('Kavya Menon', '/positions')
    await userEvent.click((await screen.findAllByRole('button', { name: /Start hiring for Backend Engineer, Engineering/ }))[0]!)   // pos-1 has req-1
    const dialog = await screen.findByRole('dialog', { name: /Start hiring/ })
    await userEvent.selectOptions(within(dialog).getByLabelText('Hiring manager'), 'e-meera')
    fireEvent.change(within(dialog).getByLabelText('Target start date'), { target: { value: '2026-12-15' } })
    await userEvent.type(within(dialog).getByLabelText('Pay range from (₹ a year)'), '1800000')
    await userEvent.type(within(dialog).getByLabelText('to (₹ a year)'), '3000000')
    fireEvent.change(within(dialog).getByLabelText('Interview time'), { target: { value: '2026-11-20T10:00' } })
    await userEvent.selectOptions(within(dialog).getByLabelText('Comp band for the offer'), 'cb-1')
    await userEvent.type(within(dialog).getByLabelText('Proposed base pay (₹ a year)'), '2400000')
    await fillNewHireDetails(dialog)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Open requisition' }))
    expect(await screen.findByText('A hire was already in progress for this position, so this is that one.')).toBeInTheDocument()
  })
})

describe('reference data', () => {
  it('lets HR edit a comp band and add a skill, with forms from the contract', async () => {
    await visit('Kavya Menon', '/reference-data')
    await userEvent.click(await screen.findByRole('button', { name: 'Comp bands' }))
    await userEvent.click((await screen.findAllByRole('button', { name: 'Edit comp band' }))[0]!)
    const dialog = await screen.findByRole('dialog', { name: 'Edit comp band' })
    const max = within(dialog).getByLabelText(/^Maximum/)
    await userEvent.clear(max); await userEvent.type(max, '3200000')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByText('₹32,00,000')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Skills' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Add skill' }))
    const form = await screen.findByRole('dialog', { name: 'Add skill' })
    await userEvent.type(within(form).getByLabelText(/^Name/), 'Kubernetes')
    await userEvent.type(within(form).getByLabelText(/^Category/), 'Platform')
    await userEvent.click(within(form).getByRole('button', { name: 'Add' }))
    expect(await screen.findByText('Kubernetes')).toBeInTheDocument()
  })

  it('shows IT the access templates it owns, and what it cannot pick from', async () => {
    await visit('Sana Qureshi', '/reference-data')
    await userEvent.click(await screen.findByRole('button', { name: 'Access templates' }))
    expect(await screen.findByText('Email, Source control, Issue tracker')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Job profiles' })).toBeNull()          // IT cannot read job profiles
    await userEvent.click(screen.getByRole('button', { name: 'Add access role template' }))
    const form = await screen.findByRole('dialog', { name: 'Add access role template' })
    // IT may write a template but cannot read job profiles, so the picker has nothing to offer.
    expect(within(form).getByLabelText(/^Job profile/)).toHaveTextContent('Nothing to choose from')
    await userEvent.click(within(form).getByRole('button', { name: 'Cancel' }))
    await userEvent.click(screen.getByRole('button', { name: 'Skills' }))
    expect(await screen.findByText(/Your role can view this but not change it\./)).toBeInTheDocument()
  })
})

describe('overview', () => {
  it('summarises hiring for the roles that can see requisitions', async () => {
    await visit('Kavya Menon', '/')
    const panel = (await screen.findByRole('heading', { name: 'Hiring' })).closest('section')!
    expect(await within(panel).findByText('Open seats')).toBeInTheDocument()
    expect(within(panel).getByText('Waiting for budget approval').nextElementSibling).toHaveTextContent('1')
    await visit('Arjun Rao', '/')
    await screen.findByRole('heading', { name: 'Your session' })
    expect(screen.queryByRole('heading', { name: 'Hiring' })).toBeNull()
  })
})

describe('accessibility of the hire screens', () => {
  it('has no automated violations on positions, the dialog, requisitions and reference data', async () => {
    let r = await visit('Kavya Menon', '/positions')
    await screen.findByRole('button', { name: 'Open seats (3)' })
    expect(await axe(r.container)).toHaveNoViolations()
    await userEvent.click((await screen.findAllByRole('button', { name: /^Start hiring for/ }))[1]!)
    await screen.findByRole('dialog', { name: /Start hiring/ })
    expect(await axe(document.body)).toHaveNoViolations()
    r = await visit('Kavya Menon', '/requisitions/req-3')
    await screen.findByRole('article', { name: 'Candidate Rahul Verma' })
    expect(await axe(r.container)).toHaveNoViolations()
    r = await visit('Kavya Menon', '/reference-data')
    await screen.findByRole('heading', { name: 'Reference data' })
    await screen.findByText('Backend Engineer')
    expect(await axe(r.container)).toHaveNoViolations()
  })
})
