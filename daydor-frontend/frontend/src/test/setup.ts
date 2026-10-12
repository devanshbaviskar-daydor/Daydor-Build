import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { toHaveNoViolations } from 'jest-axe'
import { afterEach, beforeEach, expect } from 'vitest'
import { configureTransport } from '../api/transport'
import { mockBackend } from '../mocks/router'

expect.extend(toHaveNoViolations)

beforeEach(() => {
  localStorage.clear()
  mockBackend.reset()
  configureTransport({ defaultMode: 'mock', overrides: {} })
})
afterEach(() => cleanup())
