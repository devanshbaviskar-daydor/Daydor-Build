import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import { visit } from '../test/utils'
import { consentCategories } from './privacy/PrivacyPage'

const tab = (name: string) => screen.findByRole('tab', { name })
async function openPerson(viewer: string, name: string) {
  await visit(viewer, '/people')
  await userEvent.click(await screen.findByRole('link', { name }))
  await screen.findByRole('heading', { level: 1, name })
}

describe('consent follows the employee’s country', () => {
  it('asks for the right personal details per jurisdiction, from the model', () => {
    expect(consentCategories('IN').map((c) => c.key)).toEqual(['aadhaar', 'pan', 'bank_account'])
    expect(consentCategories('US').map((c) => c.key)).toEqual(['ssn', 'bank_account'])
    expect(consentCategories('IN').find((c) => c.key === 'bank_account')?.purpose).toBe('payroll_disbursal')
  })

  it('lets an employee give and withdraw consent for each detail', async () => {
    await visit('Arjun Rao', '/my/privacy')
    expect(await screen.findByRole('heading', { name: 'Aadhaar' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Ssn' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Give consent for Pan' }))
    const pan = (await screen.findByRole('heading', { name: 'Pan' })).closest('li')!
    expect(await within(pan).findByText(/Consent given/)).toBeInTheDocument()
    await userEvent.click(within(pan).getByRole('button', { name: 'Withdraw consent for Pan' }))
    const dialog = await screen.findByRole('dialog', { name: /Withdraw consent: Pan/ })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Withdraw consent' }))
    expect(await within(pan).findByText(/Withdrawn/)).toBeInTheDocument()
    expect(within(pan).getByRole('button', { name: 'Give consent for Pan' })).toBeInTheDocument()
  })

  it('is only for employees', async () => {
    await visit('Kavya Menon', '/')
    expect(within(screen.getByRole('navigation', { name: 'Primary' })).queryByRole('link', { name: 'My privacy' })).toBeNull()
    await visit('Arjun Rao', '/')
    expect(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: 'My privacy' })).toBeInTheDocument()
  })
})

describe('people', () => {
  it('searches and filters the directory', async () => {
    await visit('Kavya Menon', '/people')
    expect(await screen.findByText('4 people')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Search by name or email'), 'isha')
    expect(await screen.findByText('1 person')).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Search by name or email'))
    await userEvent.selectOptions(screen.getByLabelText('Department'), 'dept-eng')
    expect(await screen.findByText('2 people')).toBeInTheDocument()
  })

  it('shows sensitive details by consent, and only the ones that apply in the person’s country', async () => {
    await openPerson('Kavya Menon', 'Isha Nair')
    const sens = (await screen.findByRole('heading', { name: 'Sensitive details' })).closest('section')!
    const pan = within(sens).getByText('Pan').closest('.field')!
    expect(await within(pan as HTMLElement).findByText(/Collected\./)).toBeInTheDocument()
    expect(within(sens.querySelector('dl')!).getByText('Bank account').closest('.field')).toHaveTextContent('Not collected until the employee gives consent.')
    expect(within(sens).queryByText('Ssn')).toBeNull()
    await openPerson('Kavya Menon', 'John Carter')
    const us = (await screen.findByRole('heading', { name: 'Sensitive details' })).closest('section')!
    expect(within(us).getByText('Ssn')).toBeInTheDocument()
    expect(within(us).queryByText('Pan')).toBeNull()
    expect(screen.getByText(/United States/)).toBeInTheDocument()
  })

  it('shows job and pay with the fields for the person’s country', async () => {
    await openPerson('Kavya Menon', 'Isha Nair')
    await userEvent.click(await tab('Job and pay'))
    expect(await screen.findByText('₹14,40,000')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Tax regime election' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Flsa status' })).toBeNull()
    await openPerson('Kavya Menon', 'John Carter')
    await userEvent.click(await tab('Job and pay'))
    expect(await screen.findByRole('columnheader', { name: 'Flsa status' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Tax regime election' })).toBeNull()
  })

  it('lets HR add an emergency contact and tells a manager who can change them', async () => {
    await openPerson('Kavya Menon', 'Isha Nair')
    await userEvent.click(await tab('Emergency contacts'))
    expect(await screen.findByText('Anil Nair')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Add a contact' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add an emergency contact' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add contact' }))
    expect(within(dialog).getAllByText('Required').length).toBeGreaterThan(2)
    await userEvent.type(within(dialog).getByLabelText(/^Contact name/), 'Sunita Nair')
    await userEvent.type(within(dialog).getByLabelText(/^Relationship/), 'Mother')
    await userEvent.type(within(dialog).getByLabelText(/^Phone/), '+91 98450 55555')
    await userEvent.type(within(dialog).getByLabelText(/^Priority/), '2')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add contact' }))
    expect(await screen.findByText('Sunita Nair')).toBeInTheDocument()

    await openPerson('Meera Iyer', 'Isha Nair')
    await userEvent.click(await tab('Emergency contacts'))
    expect(await screen.findByText('Only HR and the employee can change these.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add a contact' })).toBeNull()
  })

  it('lets HR rate a skill; managers can only read ratings', async () => {
    await openPerson('Kavya Menon', 'Isha Nair')
    await userEvent.click(await tab('Skills'))
    expect(await screen.findByText('Recruiting')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Rate a skill' }))
    const dialog = await screen.findByRole('dialog', { name: 'Rate a skill' })
    await userEvent.selectOptions(within(dialog).getByLabelText(/^Skill/), 'sk-4')
    await userEvent.type(within(dialog).getByLabelText(/Level/), '4')
    await userEvent.type(within(dialog).getByLabelText(/^Source/), 'manager_rated')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save rating' }))
    expect(await screen.findByText('Negotiation')).toBeInTheDocument()

    await openPerson('Meera Iyer', 'Isha Nair')
    await userEvent.click(await tab('Skills'))
    expect(await screen.findByText(/Only HR can rate skills/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rate a skill' })).toBeNull()
  })

  it('shows access with a test identity provider and links off-template access to its approval', async () => {
    await openPerson('Kavya Menon', 'Isha Nair')
    await userEvent.click(await tab('Access'))
    expect(await screen.findByText('Test identity provider')).toBeInTheDocument()
    const grants = screen.getByRole('heading', { name: 'App access' }).closest('section')!
    expect(within(grants).getByText('Production database')).toBeInTheDocument()
    expect(within(grants).getByRole('link', { name: 'Open approval' })).toHaveAttribute('href', '/approvals/ap-5')
    expect(within(grants).getAllByText('Standard access')).toHaveLength(2)
  })

  it('shows the India payroll profile and a payslip, flagged as a test bank', async () => {
    await openPerson('Kavya Menon', 'Isha Nair')
    await userEvent.click(await tab('Payroll and payslips'))
    expect(await screen.findByText('101234567890')).toBeInTheDocument()
    expect(screen.getByText('Uan number')).toBeInTheDocument()
    expect(screen.queryByText('W4 elections')).toBeNull()
    expect(screen.getByText('Test bank')).toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: /View payslip issued/ }))
    const dialog = await screen.findByRole('dialog', { name: /Payslip/ })
    expect(await within(dialog).findByText('Provident fund')).toBeInTheDocument()
    expect(within(dialog).getByText('-₹5,880')).toBeInTheDocument()
    expect(within(dialog).getByText(/Take-home ₹86,400/)).toBeInTheDocument()
  })

  it('shows the US payroll profile for a US employee', async () => {
    await openPerson('Kavya Menon', 'John Carter')
    await userEvent.click(await tab('Payroll and payslips'))
    expect(await screen.findByText('W4 elections')).toBeInTheDocument()
    expect(screen.getByText(/filing_status/)).toBeInTheDocument()
    expect(screen.queryByText('Uan number')).toBeNull()
    expect(screen.getByText(/Showing US fields/)).toBeInTheDocument()
  })

  it('lists consent and documents without opening them', async () => {
    await openPerson('Kavya Menon', 'Isha Nair')
    await userEvent.click(await tab('Consent and documents'))
    const consent = (await screen.findByRole('heading', { name: 'Consent' })).closest('section')!
    expect(await within(consent).findAllByText('Granted')).toHaveLength(2)
    const docs = screen.getByRole('heading', { name: 'Documents' }).closest('section')!
    expect(await within(docs).findByText('Offer letter')).toBeInTheDocument()
    expect(within(docs).getByText(/opening them needs the document store/)).toBeInTheDocument()
  })

  it('applies the database’s row scope: employees see themselves, managers their reports', async () => {
    await visit('Arjun Rao', '/people/e-isha')
    expect(await screen.findByRole('heading', { name: 'Person not visible' })).toBeInTheDocument()
    await visit('Arjun Rao', '/people/e-arjun')
    expect(await screen.findByRole('heading', { level: 1, name: 'Arjun Rao' })).toBeInTheDocument()
    await visit('Meera Iyer', '/people/e-john')
    expect(await screen.findByRole('heading', { name: 'Person not visible' })).toBeInTheDocument()
    await visit('Meera Iyer', '/people/e-isha')
    expect(await screen.findByRole('heading', { level: 1, name: 'Isha Nair' })).toBeInTheDocument()
  })

  it('has no People entry for the auditor and Daydor admin', async () => {
    for (const who of ['Imran Khan', 'Daydor Admin']) {
      await visit(who, '/')
      expect(within(screen.getByRole('navigation', { name: 'Primary' })).queryByRole('link', { name: 'People' })).toBeNull()
    }
  })
})

describe('onboarding and work authorization', () => {
  it('shows a new hire’s checklist by owner, what blocks day one, and the test identity provider', async () => {
    await visit('Kavya Menon', '/onboarding')
    const card = await screen.findByRole('article', { name: 'Onboarding for Isha Nair' })
    expect(within(card).getByText('2 of 4 tasks done')).toBeInTheDocument()
    expect(await within(card).findByText('Test identity provider')).toBeInTheDocument()
    for (const owner of ['Hr', 'It', 'Payroll']) expect(within(card).getByRole('region', { name: `${owner} tasks` })).toBeInTheDocument()
    const laptop = within(card).getByText('Prepare a laptop').closest('li')!
    expect(within(laptop).getByText('Needed before day one')).toBeInTheDocument()
    expect(within(laptop).getByText(/Due:/)).toBeInTheDocument()
    expect(within(card).getByText('Collect identity documents').closest('li')).toHaveTextContent(/Done/)
  })

  it('shows an employee only their own checklist, which is none until they have one', async () => {
    await visit('Arjun Rao', '/onboarding')
    expect(await screen.findByText(/Nobody is onboarding right now/)).toBeInTheDocument()
  })

  it('shows US work authorization with a live countdown, and explains it is US only', async () => {
    await visit('Kavya Menon', '/work-authorization')
    expect(await screen.findByText(/For US employees only/)).toBeInTheDocument()
    const row = (await screen.findByText('John Carter')).closest('tr')!
    expect(within(row).getByText('H-1B')).toBeInTheDocument()
    expect(within(row).getByText('Test E-Verify')).toBeInTheDocument()
    expect(within(row).getByText(/\d+ days? left/)).toBeInTheDocument()
  })

  it('masks the type for the founder and hides the page from roles without access', async () => {
    await visit('Rohan Mehta', '/work-authorization')
    const row = (await screen.findByText('John Carter')).closest('tr')!
    expect(within(row).getAllByText('Masked').length).toBeGreaterThan(0)
    await visit('Meera Iyer', '/work-authorization')
    expect(within(screen.getByRole('navigation', { name: 'Primary' })).queryByRole('link', { name: 'Work authorization' })).toBeNull()
    expect(await screen.findByRole('alert')).toHaveTextContent('Your role does not have access to this.')
  })
})

describe('accessibility of the people screens', () => {
  it('has no automated violations on the directory, each profile tab, privacy, onboarding and work authorization', async () => {
    let r = await visit('Kavya Menon', '/people')
    await screen.findByText('4 people')
    expect(await axe(r.container)).toHaveNoViolations()
    await userEvent.click(await screen.findByRole('link', { name: 'Isha Nair' }))
    await screen.findByRole('heading', { name: 'Sensitive details' })
    expect(await axe(r.container)).toHaveNoViolations()
    for (const name of ['Job and pay', 'Emergency contacts', 'Skills', 'Access', 'Payroll and payslips', 'Consent and documents']) {
      await userEvent.click(await tab(name))
      await screen.findByRole('tabpanel')
      await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull())
      expect(await axe(r.container)).toHaveNoViolations()
    }
    r = await visit('Arjun Rao', '/my/privacy')
    await screen.findByRole('heading', { name: 'Aadhaar' })
    expect(await axe(r.container)).toHaveNoViolations()
    r = await visit('Kavya Menon', '/onboarding')
    await screen.findByRole('article', { name: 'Onboarding for Isha Nair' })
    expect(await axe(r.container)).toHaveNoViolations()
    r = await visit('Kavya Menon', '/work-authorization')
    await screen.findByText('John Carter')
    expect(await axe(r.container)).toHaveNoViolations()
    fireEvent.keyDown(document, { key: 'Escape' })
  })
})
