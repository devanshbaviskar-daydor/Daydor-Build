import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { createMemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { App, makeQueryClient } from './App'
import { routesForTest } from './routes'

function renderApp(path = '/') {
  const router = createMemoryRouter(routesForTest, { initialEntries: [path] })
  return render(<App client={makeQueryClient()} router={router as never} />)
}
async function signInAs(name: string) {
  await userEvent.click(await screen.findByRole('button', { name: `Sign in as ${name}` }))
  await screen.findByRole('navigation', { name: 'Primary' })
}

describe('sign-in and shell', () => {
  it('sends people who are not signed in to the sign-in page', async () => {
    renderApp('/approvals')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('shows each role only the screens it can use', async () => {
    renderApp()
    await signInAs('Arjun Rao') // employee: approvals visible (E reads approval_request), positions not
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getByRole('link', { name: 'Approvals' })).toBeInTheDocument()
    expect(within(nav).queryByText('Positions')).toBeNull()
  })

  it('shows the sample-data badge in mock mode and signs out', async () => {
    renderApp()
    await signInAs('Rohan Mehta')
    expect(screen.getByText('Sample data')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
})

describe('saved sessions', () => {
  it('drops a session saved by an older version instead of crashing, and asks to sign in again', async () => {
    // What the FE-0 preview left in the browser: no capabilities field, under the old key.
    localStorage.setItem('daydor.session', JSON.stringify({ token: 'mock-id-founder', session: { id: 'id-founder', role: 'tenant_founder', role_label: 'Founder', display_name: 'Rohan Mehta' } }))
    localStorage.setItem('daydor.session.v3', JSON.stringify({ token: 'mock-id-founder', session: { id: 'id-founder', role: 'tenant_founder', role_label: 'Founder', display_name: 'Rohan Mehta' } }))
    renderApp('/')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(localStorage.getItem('daydor.session')).toBeNull()
    expect(localStorage.getItem('daydor.session.v3')).toBeNull()
  })
  it('keeps a current session across a reload', async () => {
    const first = renderApp('/')
    await signInAs('Rohan Mehta')
    first.unmount()
    renderApp('/')
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
  })
})

const budgetCard = async () => (await screen.findAllByRole('article')).find((a) => within(a).queryByText('Requisition budget sign-off') && within(a).queryByText('Waiting for approval'))!

describe('approvals', () => {
  it('lets the founder approve a budget request and then shows it as resolved', async () => {
    renderApp('/approvals')
    await signInAs('Rohan Mehta')
    const budget = await budgetCard()
    expect(within(budget).getByText('Requisition budget sign-off')).toBeInTheDocument()
    await userEvent.type(within(budget).getByLabelText('Note (optional)'), 'Within plan')
    await userEvent.click(within(budget).getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.getAllByRole('article').filter((a) => within(a).queryByText('Waiting for approval') && within(a).queryByText('Requisition budget sign-off'))).toHaveLength(0))
    await userEvent.click(screen.getByRole('button', { name: /^Resolved/ }))
    expect(await screen.findByText('Note: Within plan')).toBeInTheDocument()
  })

  it('shows HR the same request without approve buttons, and says who can approve', async () => {
    renderApp('/approvals')
    await signInAs('Kavya Menon')
    const budget = await budgetCard()
    expect(within(budget).queryByRole('button', { name: 'Approve' })).toBeNull()
    expect(within(budget).getByText('Waiting for Founder / owner.')).toBeInTheDocument()
  })

  it('shows a clear message when a role cannot see approvals at all', async () => {
    renderApp('/approvals')
    await signInAs('Daydor Admin')
    expect(await screen.findByRole('alert')).toHaveTextContent('Your role does not have access to this.')
  })
})

describe('design primitives page', () => {
  it('renders every state and has no automated accessibility violations', async () => {
    const { container } = renderApp('/dev/primitives')
    await signInAs('Rohan Mehta')
    expect(await screen.findByRole('heading', { name: 'Design primitives' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
