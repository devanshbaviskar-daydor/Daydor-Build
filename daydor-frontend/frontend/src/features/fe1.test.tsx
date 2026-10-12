import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import { renderApp, signInAs } from '../test/utils'

const card = (name: string) => screen.findByRole('article', { name })

describe('approvals inbox', () => {
  it('counts each tab, puts what you can act on first, and filters by kind', async () => {
    renderApp('/approvals')
    await signInAs('Rohan Mehta')
    expect(await screen.findByRole('button', { name: 'Waiting (4)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Resolved (4)' })).toBeInTheDocument()
    const articles = screen.getAllByRole('article')
    // The founder can decide the budget and offer-band requests; those come before the IT and HR ones.
    expect(within(articles[0]!).getByText('Requisition budget sign-off')).toBeInTheDocument()
    expect(within(articles[1]!).getByText('Offer or comp change outside band')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Kind of approval'), 'g_offer_band')
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Waiting (1)' })).toBeInTheDocument()
  })

  it('makes maker-checker visible: HR cannot approve a request HR raised', async () => {
    renderApp('/approvals')
    await signInAs('Kavya Menon')
    const mine = await card('Identity account approval')
    expect(within(mine).getByText('You raised this request, so someone else has to approve it.')).toBeInTheDocument()
    expect(within(mine).queryByRole('button', { name: 'Approve' })).toBeNull()
  })

  it('links every card to its details', async () => {
    renderApp('/approvals')
    await signInAs('Rohan Mehta')
    const first = (await screen.findAllByRole('article'))[0]!
    await userEvent.click(within(first).getByRole('link', { name: 'Details' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Requisition budget sign-off' })).toBeInTheDocument()
  })
})

describe('approval details, for a role that can read workflows', () => {
  it('shows the paused workflow, then moves it on when the founder approves', async () => {
    renderApp('/approvals/ap-1')
    await signInAs('Rohan Mehta')
    const steps = await screen.findByRole('list', { name: 'Workflow steps' })
    const current = within(steps).getAllByRole('listitem').find((li) => li.getAttribute('aria-current') === 'step')!
    expect(within(current).getByText('Waiting on a person to approve')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Note (optional)'), 'Within plan')
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => {
      const now = within(screen.getByRole('list', { name: 'Workflow steps' })).getAllByRole('listitem').find((li) => li.getAttribute('aria-current') === 'step')!
      expect(within(now).getByText('Job posting')).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
    expect(screen.getByText('Note: Within plan')).toBeInTheDocument()
  })

  it('shows recorded pre-check results as shadow mode, never applied', async () => {
    renderApp('/approvals/ap-5')
    await signInAs('Kavya Menon')
    const panel = (await screen.findByRole('heading', { name: 'Automated pre-check' })).closest('section')!
    expect(await within(panel).findByText(/Pre-check result:/)).toHaveTextContent('Needs a person')
    expect(within(panel).getByText(/41% sure/)).toBeInTheDocument()
    expect(within(panel).getByText('Shadow mode, not applied')).toBeInTheDocument()
    expect(within(panel).getByText(/A person decides either way/)).toBeInTheDocument()
  })

  it('says so plainly when no pre-check was recorded', async () => {
    renderApp('/approvals/ap-1')
    await signInAs('Rohan Mehta')
    expect(await screen.findByText('No automated pre-check was recorded for this request.')).toBeInTheDocument()
  })

  it('shows a clear message for a request that does not exist', async () => {
    renderApp('/approvals/nope')
    await signInAs('Rohan Mehta')
    expect(await screen.findByRole('heading', { name: 'Request not found' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('That request was not found.')
  })
})

describe('approval details, for a role that cannot read workflows', () => {
  it('gives IT a plain status line instead of a timeline, and lets IT decide', async () => {
    renderApp('/approvals/ap-5')
    await signInAs('Sana Qureshi')
    expect(await screen.findByText(/Waiting for IT admin to decide: .*Raised/)).toBeInTheDocument()
    expect(screen.getByText(/Your role cannot see workflow timelines, so this is the status of the approval itself\./)).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Workflow steps' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Automated pre-check' })).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(await screen.findByText(/^Approved on .*: /)).toBeInTheDocument()
  })

  it('does not list Workflows for them and explains if they open it directly', async () => {
    renderApp('/workflows')
    await signInAs('Meera Iyer')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).queryByRole('link', { name: 'Workflows' })).toBeNull()
    expect(await screen.findByRole('alert')).toHaveTextContent('Your role cannot see workflow timelines.')
  })
})

describe('workflows', () => {
  it('lists workflows for roles that can read them, filtered by status', async () => {
    renderApp('/workflows')
    await signInAs('Rohan Mehta')
    const rows = (await screen.findAllByRole('link', { name: /Hire: Job requisition/ })).map((l) => l.closest('tr')!)
    expect(rows).toHaveLength(3)
    const budget = rows.find((r) => within(r).queryByText('Approval request'))!
    expect(within(budget).getByText('Waiting for approval')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Stopped' }))
    expect(await screen.findByText('No workflows match this filter.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Completed' }))
    expect(await screen.findAllByRole('link', { name: /Hire: Job requisition/ })).toHaveLength(1)
  })

  it('shows the steps, what happened and the details a workflow carries, without personal values', async () => {
    renderApp('/workflows/wf-1')
    await signInAs('Rohan Mehta')
    expect(await screen.findByRole('heading', { level: 1, name: 'Hire workflow' })).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Workflow steps' })).toBeInTheDocument()
    const log = screen.getByRole('heading', { name: 'What happened' }).closest('section')!
    expect(within(log).getAllByRole('row')).toHaveLength(5) // header, three moves and the pause at the gate
    const ctx = screen.getByRole('heading', { name: 'Details the workflow carries' }).closest('section')!
    expect(within(ctx).getByText('Channel')).toBeInTheDocument()
    expect(within(ctx).queryByText(/email|phone|full name/i)).toBeNull()
    expect(screen.getByRole('link', { name: 'Open the approval' })).toHaveAttribute('href', '/approvals/ap-1')
  })

  it('opens the audit trail with approvals and workflow steps in time order', async () => {
    renderApp('/approvals/ap-1')
    await signInAs('Rohan Mehta')
    await userEvent.click(await screen.findByRole('button', { name: 'View audit trail' }))
    const drawer = await screen.findByRole('dialog', { name: /Audit trail/ })
    expect(await within(drawer).findByText('Asked for approval: Requisition budget sign-off')).toBeInTheDocument()
    expect(within(drawer).getByText('Paused at approval request, waiting for approval')).toBeInTheDocument()
    expect(within(drawer).queryByText(/Your role cannot see workflow steps/)).toBeNull()
  })

  it('tells a role without workflow access what its trail leaves out', async () => {
    renderApp('/approvals/ap-1')
    await signInAs('Meera Iyer')
    await userEvent.click(await screen.findByRole('button', { name: 'View audit trail' }))
    const drawer = await screen.findByRole('dialog', { name: /Audit trail/ })
    expect(await within(drawer).findByText(/Your role cannot see workflow steps, so they are not listed here\./)).toBeInTheDocument()
    expect(within(drawer).getByText('Asked for approval: Requisition budget sign-off')).toBeInTheDocument()
  })
})

describe('overview', () => {
  it('links straight to a request and summarises workflows for roles that can read them', async () => {
    renderApp('/')
    await signInAs('Rohan Mehta')
    expect(await screen.findByText('2 waiting for approval, 0 in progress.')).toBeInTheDocument()
    const wait = screen.getByRole('heading', { name: 'Waiting for you' }).closest('section')!
    expect((await within(wait).findAllByRole('link', { name: 'Review' }))[0]).toHaveAttribute('href', expect.stringMatching(/^\/approvals\/ap-/))
  })
  it('hides the workflow summary from roles that cannot read workflows', async () => {
    renderApp('/')
    await signInAs('Arjun Rao')
    await screen.findByRole('heading', { name: 'Your session' })
    expect(screen.queryByRole('heading', { name: 'Workflows' })).toBeNull()
  })
})

describe('accessibility', () => {
  it('has no automated violations on the approval and workflow pages', async () => {
    const a = renderApp('/approvals/ap-5')
    await signInAs('Kavya Menon')
    await screen.findByRole('heading', { name: 'Automated pre-check' })
    await screen.findByText(/Pre-check result:/)
    expect(await axe(a.container)).toHaveNoViolations()
    a.unmount(); localStorage.clear()

    const b = renderApp('/workflows/wf-1')
    await signInAs('Rohan Mehta')
    await screen.findByRole('heading', { name: 'What happened' })
    expect(await axe(b.container)).toHaveNoViolations()
    b.unmount(); localStorage.clear()

    const c = renderApp('/approvals')
    await signInAs('Rohan Mehta')
    await screen.findAllByRole('article')
    expect(await axe(c.container)).toHaveNoViolations()
  })
})
