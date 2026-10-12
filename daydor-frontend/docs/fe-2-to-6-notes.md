# FE-2 to FE-6 notes (the Hire flow)

## What is live and what is sample data

| Screen | Status |
| --- | --- |
| Positions, Start hiring, Requisitions, candidate pipeline (screening, interview, offer), out-of-band offer approval | **Live-ready, tested on real Postgres with the queue worker** |
| Reference data, People directory, person profile (overview, job, contacts, skills, consent and documents), My privacy | **Live-ready.** They read and write tables that exist today. Contacts, consent and skill ratings were tested live |
| Background check step, Onboarding, Work authorization, Access, Payroll profile, Payslips | **Sample data only.** The tables exist in the model but the backend steps that fill them (its Sprints 3 to 5) are not built, so live shows empty states |

So the Hire flow is demoable end to end in the preview, and live up to the offer.

## Built

- **API:** requisition list and detail with a candidate pipeline, application entry, a directory endpoint, multi-value filters (`?id__in=a,b`), direct writes for consent records and checklist tasks. 45 tests.
- **Frontend:** nine new screens, a start-hire dialog, an application dialog, reusable `ModelTable` and `ModelForm` generated from the contract (references become pickers, listed enums selects, unlisted enums free text), a modal dialog, jurisdiction-aware profile and consent. 99 tests including accessibility checks on every new screen, plus 6 live end-to-end tests.
- **Mock backend:** now mirrors the real hire flow (budget approval, posting, application, AEDT sign-off, interview, offer, out-of-band approval) and the database's row scope (employees see themselves, managers their reports).

## Found in the backend or model (nothing requested; the UI works around each)

1. **One candidate per hire.** After the posting step the workflow waits for an application, and entering one moves it on, so a requisition can take exactly one candidate through screening, interview and offer. The pipeline UI says so.
2. **Every gate approval is raised against the requisition**, not against the screening or offer row. The pipeline matches approvals to steps by gate type.
3. **Hiring managers cannot see candidates.** The database hides a candidate row from managers until `converted_employee_id` is set, so a hiring manager sees the application and masked screening but not who the candidate is. This looks unintended for the person doing the interview.
4. **Only HR can rate a skill.** Employees and managers cannot set `proficiency_level` (class C2), which contradicts the plan. The UI shows ratings read-only for them.
5. **IT can write access templates but cannot read job profiles**, so IT cannot pick the job profile for a new template.
6. **Start-hire context** also carries the comp band, proposed base and equity, not only the interviewer and time.
7. **`document` and `checklist_task` have no person-scope row policy**, so employees may be able to read other people's rows. The UI only ever asks for its own, so this is not visible in the app, but it is worth a security look.
8. **Several enum value lists are unknown** (position status, application stage, task status, work authorization type). The UI shows raw values humanized and uses free text in forms.

## Decisions made on the frontend side

| Decision | Reason |
| --- | --- |
| Consent categories and jurisdictions come from the model's encrypted employee columns: Aadhaar and PAN for India, SSN for the US, bank account for both | Generated, not typed. The purpose per category (identity verification, payroll disbursal) is my assumption until the backend defines the consent flow |
| Application entry is HR-only, and only while a posting is live | Matches the backend trigger and the `application` write grant |
| A second Start hiring for the same position opens the existing hire | The API now returns it instead of failing |
| Directory capability comes from the session, not a role list in the UI | It is a backend grant fact |

## Not done or not verified

- No screenshots (no browser available). Layout is verified by tests and the accessibility checker only.
- Task completion in Onboarding is read-only: the task status values are unknown, so writing "done" would be a guess.
- No document upload or download: no document store exists.
- Payslips and bank payments are display only. No tax logic is shown, so there is no illustrative label yet.
- `.github/workflows/ci.yml` has still never run.

## Asks for the backend

None blocking. Items 3, 4 and 7 above are worth a decision from the backend side.
