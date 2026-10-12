import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Approval, ApplicationBody, AuditTrail, DirectoryRow, Evaluation, RequisitionDetail, RequisitionSummary, Session, StartHireBody, TableRows, WorkflowInstance, WorkflowTransitionRow } from './types'
import type { WorkflowDefinition } from '../ui'

export const useDevUsers = () => useQuery({ queryKey: ['dev-users'], queryFn: () => api.get<{ users: Session[] }>('/auth/dev-users') })

export function useApprovals(status?: string) {
  return useQuery({
    queryKey: ['approvals', status ?? 'all'],
    queryFn: () => api.get<{ approvals: Approval[] }>(`/approvals${status ? `?status=${status}` : ''}`),
    refetchInterval: 15_000, // no push channel exists, so poll
  })
}

export function useApprovalsFor(subjectId: string | undefined) {
  return useQuery({
    queryKey: ['approvals', 'subject', subjectId],
    enabled: !!subjectId,
    queryFn: () => api.get<{ approvals: Approval[] }>(`/approvals?subject_id=${subjectId}`),
    refetchInterval: 15_000,
  })
}

export function useResolveApproval() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; decision: 'approved' | 'rejected'; note?: string }) =>
      api.post<{ id: string; status: string }>(`/approvals/${v.id}/resolve`, { decision: v.decision, note: v.note || undefined }, `resolve-${v.id}-${v.decision}`),
    onSettled: () => { for (const k of ['approvals', 'approval', 'workflow', 'audit']) void qc.invalidateQueries({ queryKey: [k] }) },
  })
}

export const useWorkflowInstance = (id: string | null) => useQuery({
  queryKey: ['workflow', id], enabled: !!id, retry: false,
  queryFn: () => api.get<{ instance: WorkflowInstance; transitions: WorkflowTransitionRow[]; definition: WorkflowDefinition }>(`/workflows/instances/${id}`),
})

export const useWorkflowInstances = (status?: string) => useQuery({
  queryKey: ['workflow', 'list', status ?? 'all'], retry: false, refetchInterval: 15_000,
  queryFn: () => api.get<{ instances: WorkflowInstance[] }>(`/workflows/instances${status ? `?status=${status}` : ''}`),
})

export const useWorkflowInstancesFor = (subjectTable: string) => useQuery({
  queryKey: ['workflow', 'list', 'subject_table', subjectTable], retry: false, refetchInterval: 15_000,
  queryFn: () => api.get<{ instances: WorkflowInstance[] }>(`/workflows/instances?subject_table=${subjectTable}&limit=200`),
})

export const useWorkflowInstanceFor = (subjectTable: string, subjectId: string | undefined) => useQuery({
  queryKey: ['workflow', 'list', 'subject', subjectTable, subjectId], enabled: !!subjectId, retry: false, refetchInterval: 15_000,
  queryFn: () => api.get<{ instances: WorkflowInstance[] }>(`/workflows/instances?subject_table=${subjectTable}&subject_id=${subjectId}`),
})

export const useTable = (table: string, params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString()
  return useQuery({ queryKey: ['table', table, qs], retry: false, queryFn: () => api.get<TableRows>(`/tables/${table}${qs ? `?${qs}` : ''}`) })
}

export const useApproval = (id: string | undefined) => useQuery({
  queryKey: ['approval', id], enabled: !!id, retry: false, refetchInterval: 15_000,
  queryFn: () => api.get<Approval>(`/approvals/${id}`),
})

export const useAuditTrail = (table: string, id: string, enabled: boolean) => useQuery({
  queryKey: ['audit', table, id], enabled, retry: false,
  queryFn: () => api.get<AuditTrail>(`/audit/subject?table=${encodeURIComponent(table)}&id=${encodeURIComponent(id)}`),
})

export const useEvaluations = (params: { approval_id?: string; subject_table?: string; subject_id?: string }, enabled: boolean) => {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString()
  return useQuery({ queryKey: ['evaluations', qs], enabled, retry: false, queryFn: () => api.get<{ evaluations: Evaluation[] }>(`/evaluations?${qs}`) })
}

const everything = ['approvals', 'approval', 'workflow', 'audit', 'requisitions', 'requisition', 'table', 'directory']
const refreshAll = (qc: ReturnType<typeof useQueryClient>) => { for (const k of everything) void qc.invalidateQueries({ queryKey: [k] }) }

export const useRequisitions = () => useQuery({
  queryKey: ['requisitions'], retry: false, refetchInterval: 10_000,
  queryFn: () => api.get<{ requisitions: RequisitionSummary[] }>('/hire/requisitions'),
})
export const useRequisition = (id: string | undefined) => useQuery({
  queryKey: ['requisition', id], enabled: !!id, retry: false, refetchInterval: 10_000,
  queryFn: () => api.get<RequisitionDetail>(`/hire/requisitions/${id}`),
})
export function useStartHire() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { body: StartHireBody; key: string }) => api.post<{ instance_id: string; requisition_id: string; existing?: boolean }>('/hire/start', v.body, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useEnterApplication(requisitionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { body: ApplicationBody; key: string }) => api.post<{ status: string }>(`/hire/requisitions/${requisitionId}/applications`, v.body, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useRequestConsent(requisitionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => api.post<{ status: string }>(`/hire/requisitions/${requisitionId}/request-consent`, {}, key),
    onSettled: () => refreshAll(qc),
  })
}
export const useDirectory = (params: { q?: string; department_id?: string }) => {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString()
  return useQuery({ queryKey: ['directory', qs], retry: false, queryFn: () => api.get<{ rows: DirectoryRow[]; total: number }>(`/directory${qs ? `?${qs}` : ''}`) })
}
export function useCreateRow(table: string) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: (v: { values: Record<string, unknown>; key: string }) => api.post<{ id: string }>(`/tables/${table}`, v.values, v.key), onSettled: () => refreshAll(qc) })
}
export function useUpdateRow(table: string) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: (v: { id: string; values: Record<string, unknown> }) => api.patch<{ id: string }>(`/tables/${table}/${v.id}`, v.values), onSettled: () => refreshAll(qc) })
}

// FE-7: time, leave, benefits, expenses
export function useBuildTimecard() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { body: { employee_id: string; period_start: string; period_end: string }; key: string }) =>
      api.post<{ timecard_id: string; approval_request_id: string }>('/timekeeping/timecards', v.body, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useAccrueLeave() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { employee_id: string; leave_policy_id: string; as_of: string }) =>
      api.post<{ leave_balance_id: string }>('/timekeeping/leave-balances/accrue', body),
    onSettled: () => refreshAll(qc),
  })
}
export function useElectBenefit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { body: { employee_id: string; benefit_plan_id: string; coverage_tier: string; employee_cost: number; effective_from: string }; key: string }) =>
      api.post<{ benefit_election_id: string }>('/benefits/elections', v.body, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useSubmitExpense() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { body: { amount: number; category: string; receipt_document_id?: string }; key: string }) =>
      api.post<{ expense_id: string; approval_request_id: string }>('/expenses', v.body, v.key),
    onSettled: () => refreshAll(qc),
  })
}

// FE-9/FE-10: payroll runs, disbursal, filing and GL
export function useBuildPayrollRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { body: { legal_entity_id: string; period_start: string; period_end: string; retention_class_id: string }; key: string }) =>
      api.post<{ payroll_run_id: string; payslip_ids: string[]; anomaly_check: { effective_decision: string; approval_request_id: string | null } }>('/payroll/runs', v.body, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useRequestDisbursal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { runId: string; key: string }) => api.post<{ approval_request_id: string }>(`/payroll/runs/${v.runId}/request-disbursal`, {}, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useDisburse() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { runId: string; approval_request_id: string; key: string }) =>
      api.post<{ status: string }>(`/payroll/runs/${v.runId}/disburse`, { approval_request_id: v.approval_request_id }, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useIssuePayslips() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { runId: string; key: string }) => api.post<{ payslip_ids: string[] }>(`/payroll/runs/${v.runId}/issue-payslips`, {}, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useFileReturns() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { runId: string; period: string; retention_class_id: string; key: string }) =>
      api.post<{ filing_ids: string[] }>(`/payroll/runs/${v.runId}/file`, { period: v.period, retention_class_id: v.retention_class_id }, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useOpenGlEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { runId: string; key: string }) => api.post<{ gl_journal_entry_id: string; approval_request_id: string }>(`/payroll/runs/${v.runId}/gl`, {}, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function usePostGlEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { glId: string; approval_request_id: string; key: string }) =>
      api.post<{ status: string }>(`/payroll/gl/${v.glId}/post`, { approval_request_id: v.approval_request_id }, v.key),
    onSettled: () => refreshAll(qc),
  })
}

// FE-11/FE-12: exit flow -- the three actions a person triggers (every other step runs
// automatically), same create-then-gate shape as payroll disbursal (docs/integration-notes.md)
export function useStartExit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { body: { employee_id: string; termination_type: string; reason_code: string; notice_date: string; last_working_day: string }; key: string }) =>
      api.post<{ instance_id: string; termination_id: string }>('/exit/start', v.body, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useDeprovision() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { identityAccountId: string; approval_request_id: string; key: string }) =>
      api.post<{ status: string }>(`/exit/identity-accounts/${v.identityAccountId}/deprovision`, { approval_request_id: v.approval_request_id }, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useDisburseFinalSettlement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { finalSettlementId: string; approval_request_id: string; key: string }) =>
      api.post<{ status: string }>(`/exit/final-settlements/${v.finalSettlementId}/disburse`, { approval_request_id: v.approval_request_id }, v.key),
    onSettled: () => refreshAll(qc),
  })
}
export function useSendCobraNotice() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { cobraEventId: string; approval_request_id: string; key: string }) =>
      api.post<{ status: string }>(`/exit/cobra-events/${v.cobraEventId}/send-notice`, { approval_request_id: v.approval_request_id }, v.key),
    onSettled: () => refreshAll(qc),
  })
}

/** Reference tables as id -> row maps, for showing labels and filling pickers. A table the role cannot
 *  read simply yields an empty map. */
export function useLookups(tables: string[]) {
  const results = useQueries({ queries: tables.map((t) => ({
    queryKey: ['table', t, 'limit=200'], retry: false, staleTime: 30_000,
    queryFn: () => api.get<TableRows>(`/tables/${t}?limit=200`),
  })) })
  const lookups: Record<string, Record<string, Record<string, unknown>>> = {}
  tables.forEach((t, i) => { lookups[t] = Object.fromEntries((results[i]?.data?.rows ?? []).map((r) => [String(r.id), r])) })
  return { lookups, pending: results.some((r) => r.isPending) }
}
