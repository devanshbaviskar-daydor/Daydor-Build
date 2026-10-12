import { describe, expect, it } from 'vitest'
import {
  HUMAN_ROLES, canReadTable, canWriteTable, enumColumnCount, enumLabel, enumValues, fieldState, flows, gate, gates,
  humanize, jurisdictionColumns, listedEnumCount, roles, tableLevel, tableNames, visibleColumns, writableColumns,
} from './index'

describe('generated contract', () => {
  it('covers the whole model', () => {
    expect(tableNames).toHaveLength(82)
    expect(roles).toHaveLength(10)
    expect(flows.map((f) => f.id)).toContain('hire')
    expect(HUMAN_ROLES).toHaveLength(9)
    expect(HUMAN_ROLES).not.toContain('agent_<domain>')
  })

  it('knows the 23 gates, including the platform requisition gate', () => {
    expect(gates.filter((g) => g.kind === 'hard')).toHaveLength(21)
    expect(gate('g_requisition_budget')?.approvers).toEqual(['tenant_founder'])
    expect(gate('g_pay_anomaly')?.approvers).toEqual(['tenant_payroll', 'daydor_ops'])
    expect(gates.filter((g) => g.kind === 'soft').map((g) => g.id).sort()).toEqual(['sg_access_request_precheck', 'sg_payroll_anomaly_precheck'])
  })
})

describe('access levels come from the model', () => {
  it('matches the backend for tables', () => {
    expect(tableLevel('position', 'tenant_hr')).toBe(4)
    expect(tableLevel('position', 'tenant_employee')).toBe(0)
    expect(tableLevel('work_authorization', 'tenant_manager')).toBe(0)
    expect(canReadTable('approval_request', 'daydor_admin')).toBe(false)
    expect(canWriteTable('job_requisition', 'tenant_hr')).toBe(true)
    expect(canWriteTable('job_requisition', 'tenant_employee')).toBe(false)
  })

  it('classifies a single field per role', () => {
    expect(fieldState('work_authorization', 'auth_type', 'tenant_hr').kind).toBe('write')
    expect(fieldState('work_authorization', 'auth_type', 'tenant_founder').kind).toBe('masked')
    expect(fieldState('work_authorization', 'auth_type', 'tenant_employee').kind).toBe('read')
    expect(fieldState('work_authorization', 'auth_type', 'tenant_manager').kind).toBe('hidden')
    expect(fieldState('employee', 'pan_encrypted', 'tenant_hr')).toMatchObject({ kind: 'write', encrypted: true, cls: 'C3' })
  })

  it('never lists encrypted columns and never offers id or tenant columns for writing', () => {
    const cols = visibleColumns('employee', 'tenant_hr').map((c) => c.n)
    expect(cols).toContain('full_name')
    expect(cols).not.toContain('pan_encrypted')
    const w = writableColumns('position', 'tenant_hr').map((c) => c.n)
    expect(w).toContain('status')
    for (const n of ['id', 'tenant_id', 'created_at', 'updated_at']) expect(w).not.toContain(n)
  })

  it('reads jurisdiction tags from the model', () => {
    expect(jurisdictionColumns('payroll_profile', 'IN').length).toBeGreaterThan(0)
    expect(jurisdictionColumns('payroll_profile', 'US').length).toBeGreaterThan(0)
  })

  it('fails closed for an unknown field', () => {
    expect(fieldState('position', 'nope', 'tenant_hr').kind).toBe('hidden')
  })
})

describe('provisional enums', () => {
  it('lists some values and is honest that most are unknown', () => {
    expect(enumColumnCount).toBe(88)
    expect(listedEnumCount).toBeGreaterThan(5)
    expect(listedEnumCount).toBeLessThan(88)
    expect(enumValues('position', 'status')).toContain('open')
    expect(enumValues('approval_request', 'status')).toEqual(['approved', 'expired', 'pending', 'rejected'])
    expect(enumValues('offer', 'status')).toBeNull()
  })
  it('labels unknown values instead of failing', () => {
    expect(enumLabel('position', 'status', 'on_hold')).toBe('On hold')
    expect(humanize('s03_approval_request')).toBe('Approval request')
  })
})
