export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

/** What to tell the person, by error code. Falls back to the server's own wording. */
const PLAIN: Record<string, string> = {
  not_signed_in: 'Sign in to continue.',
  session_expired: 'Your session has ended. Sign in again.',
  forbidden: 'Your role does not have access to this.',
  workflow_not_visible: 'Your role cannot see workflow timelines. The approval shows its status instead.',
  maker_checker: 'You raised this request, so someone else has to approve it.',
  wrong_approver_role: 'Your role cannot approve this kind of request.',
  already_resolved: 'Someone already resolved this request. Refresh to see the result.',
  no_open_seat: 'That position is not an open, vacant, budgeted seat.',
  identity_mismatch: 'This account is not active in the platform. Ask an administrator.',
}
export const explain = (e: unknown): string =>
  e instanceof ApiError ? (PLAIN[e.code] ?? e.message) : 'Something went wrong. Try again.'
