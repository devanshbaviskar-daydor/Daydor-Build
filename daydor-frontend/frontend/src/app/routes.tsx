import { Navigate, Outlet, createBrowserRouter, createHashRouter, Link, useLocation } from 'react-router-dom'
import { useSession } from '../api/session'
import { ApprovalDetailPage } from '../features/approvals/ApprovalDetailPage'
import { ApprovalsPage } from '../features/approvals/ApprovalsPage'
import { SignInPage } from '../features/auth/SignInPage'
import { PrimitivesPage } from '../features/dev/PrimitivesPage'
import { WorkAuthorizationPage } from '../features/compliance/WorkAuthorizationPage'
import { ExitDetailPage } from '../features/exit/ExitDetailPage'
import { ExitPage } from '../features/exit/ExitPage'
import { OnboardingPage } from '../features/onboarding/OnboardingPage'
import { OverviewPage } from '../features/overview/OverviewPage'
import { PayrollPage } from '../features/payroll/PayrollPage'
import { PayrollRunDetailPage } from '../features/payroll/PayrollRunDetailPage'
import { PeoplePage } from '../features/people/PeoplePage'
import { PersonPage } from '../features/people/PersonPage'
import { PrivacyPage } from '../features/privacy/PrivacyPage'
import { ReferenceDataPage } from '../features/reference/ReferenceDataPage'
import { PositionsPage } from '../features/positions/PositionsPage'
import { RequisitionDetailPage } from '../features/requisitions/RequisitionDetailPage'
import { RequisitionsPage } from '../features/requisitions/RequisitionsPage'
import { TimeAndLeavePage } from '../features/timekeeping/TimeAndLeavePage'
import { WorkflowDetailPage } from '../features/workflows/WorkflowDetailPage'
import { WorkflowsPage } from '../features/workflows/WorkflowsPage'
import { Shell } from './shell/Shell'

function RequireSession() {
  const { session } = useSession()
  const location = useLocation()
  // Remember where the person was going, so signing in returns them there.
  return session ? <Outlet /> : <Navigate to="/sign-in" replace state={{ from: location.pathname + location.search }} />
}
function NotFound() {
  return <div className="stack"><h1>Page not found</h1><p className="muted">That page does not exist. <Link to="/" className="btn btn-quiet">Go to the overview</Link></p></div>
}

export const routesForTest = [
  { path: '/sign-in', element: <SignInPage /> },
  { element: <RequireSession />, children: [{ element: <Shell />, children: [
    { index: true, element: <OverviewPage /> },
    { path: 'approvals', element: <ApprovalsPage /> },
    { path: 'approvals/:id', element: <ApprovalDetailPage /> },
    { path: 'positions', element: <PositionsPage /> },
    { path: 'requisitions', element: <RequisitionsPage /> },
    { path: 'requisitions/:id', element: <RequisitionDetailPage /> },
    { path: 'people', element: <PeoplePage /> },
    { path: 'people/:id', element: <PersonPage /> },
    { path: 'onboarding', element: <OnboardingPage /> },
    { path: 'work-authorization', element: <WorkAuthorizationPage /> },
    { path: 'my/privacy', element: <PrivacyPage /> },
    { path: 'reference-data', element: <ReferenceDataPage /> },
    { path: 'time', element: <TimeAndLeavePage /> },
    { path: 'payroll', element: <PayrollPage /> },
    { path: 'payroll/:id', element: <PayrollRunDetailPage /> },
    { path: 'exit', element: <ExitPage /> },
    { path: 'exit/:id', element: <ExitDetailPage /> },
    { path: 'workflows', element: <WorkflowsPage /> },
    { path: 'workflows/:id', element: <WorkflowDetailPage /> },
    { path: 'dev/primitives', element: <PrimitivesPage /> },
    { path: '*', element: <NotFound /> },
  ] }] },
]
// A hosted preview has no server to answer deep links, so it routes with the URL hash.
export const makeRouter = () => (import.meta.env.MODE === 'preview' ? createHashRouter(routesForTest) : createBrowserRouter(routesForTest))
