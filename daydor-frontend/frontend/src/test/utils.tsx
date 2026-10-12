import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router-dom'
import { App, makeQueryClient } from '../app/App'
import { routesForTest } from '../app/routes'

export function renderApp(path = '/') {
  const router = createMemoryRouter(routesForTest, { initialEntries: [path] })
  return render(<App client={makeQueryClient()} router={router as never} />)
}

export async function signInAs(name: string) {
  await userEvent.click(await screen.findByRole('button', { name: `Sign in as ${name}` }))
  await screen.findByRole('navigation', { name: 'Primary' })
}

let current: ReturnType<typeof renderApp> | null = null
/** Sign in as someone at a path, replacing whoever was signed in. Sample data carries over within a test. */
export async function visit(name: string, path: string) {
  current?.unmount(); localStorage.clear()
  current = renderApp(path)
  await signInAs(name)
  return current
}
