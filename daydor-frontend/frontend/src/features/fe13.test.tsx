import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import { canReadTable } from '../contract'
import { visit } from '../test/utils'

/** FE-13 (trimmed scope): a role-matrix smoke test across every role for the FE-7..FE-12 screens
 *  (Time and leave, Payroll, Exit, Reference data), plus an accessibility pass on each. None of
 *  these screens had any frontend test coverage before this -- only the live.test.ts integration
 *  suite (which needs a running backend and is skipped otherwise) touched them at all. */

const ROLES = ['Rohan Mehta', 'Kavya Menon', 'Dev Patel', 'Sana Qureshi', 'Meera Iyer', 'Arjun Rao', 'Daydor Ops', 'Daydor Admin', 'Imran Khan']
const SCREENS: { path: string; heading: string }[] = [
  { path: '/time', heading: 'Time and leave' },
  { path: '/payroll', heading: 'Payroll' },
  { path: '/exit', heading: 'Exit' },
  { path: '/reference-data', heading: 'Reference data' },
]

describe('role matrix: every role can open every FE-7..FE-12 screen without crashing', () => {
  for (const name of ROLES) {
    it(`${name} sees a real heading (never a crash) on every new screen`, async () => {
      for (const { path, heading } of SCREENS) {
        await visit(name, path)
        expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
      }
    })
  }
})

describe('nav visibility for the new screens matches the contract, not a hardcoded role list', () => {
  const ROLE_OF: Record<string, string> = {
    'Rohan Mehta': 'tenant_founder', 'Kavya Menon': 'tenant_hr', 'Dev Patel': 'tenant_payroll',
    'Sana Qureshi': 'tenant_it', 'Meera Iyer': 'tenant_manager', 'Arjun Rao': 'tenant_employee',
    'Daydor Ops': 'daydor_ops', 'Daydor Admin': 'daydor_admin', 'Imran Khan': 'external_auditor',
  }
  it.each([['Payroll', 'payroll_run'], ['Exit', 'termination']] as const)('"%s" nav link appears exactly for roles that can read %s', async (label, table) => {
    for (const name of ROLES) {
      await visit(name, '/')
      const nav = screen.getByRole('navigation', { name: 'Primary' })
      if (canReadTable(table, ROLE_OF[name]!)) expect(within(nav).getByRole('link', { name: label })).toBeInTheDocument()
      else expect(within(nav).queryByRole('link', { name: label })).toBeNull()
    }
  })
})

describe('accessibility of the FE-7..FE-12 screens', () => {
  it('has no automated violations on Time and leave (every tab), Payroll, Exit and Reference data', async () => {
    let r = await visit('Kavya Menon', '/time')
    await screen.findByRole('heading', { level: 1, name: 'Time and leave' })
    for (const tab of ['Time', 'Leave', 'Benefits', 'Expenses']) {
      await userEvent.click(screen.getByRole('button', { name: tab }))
      await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull())
      expect(await axe(r.container)).toHaveNoViolations()
    }

    r = await visit('Dev Patel', '/payroll')
    await screen.findByRole('heading', { level: 1, name: 'Payroll' })
    expect(await axe(r.container)).toHaveNoViolations()

    r = await visit('Kavya Menon', '/exit')
    await screen.findByRole('heading', { level: 1, name: 'Exit' })
    expect(await axe(r.container)).toHaveNoViolations()

    r = await visit('Kavya Menon', '/reference-data')
    await screen.findByRole('heading', { level: 1, name: 'Reference data' })
    expect(await axe(r.container)).toHaveNoViolations()
  })
})
