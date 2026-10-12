# FE-2 to FE-6 demo script: the Hire flow

Preview (sample data) first: every screen has something to show. Live afterwards: the first half is real.

## Preview

1. **Rohan Mehta** (Founder): Overview now has a **Hiring** panel. Open **Requisitions**: one waiting for budget approval, two posted.
2. Sign in as **Kavya Menon** (HR). **Positions** → *Open seats (3)* → **Start hiring** on the second Backend Engineer seat. Submit the empty form to see the checks, then fill it: manager Meera Iyer, a start date, pay range 18 to 30 lakh, interview time, comp band, proposed base ₹24,00,000. You land on the requisition: *Waiting for budget approval*.
3. Sign in as **Rohan**, **Approvals**, approve the budget. Back as **Kavya**, open the requisition: *Posted*. **Enter an application** (Neha Gupta). Screening appears: score, placeholder screener, and *Needs a decision*.
4. As **Kavya**, approve the AEDT sign-off in **Approvals**. The requisition now shows the interview (with Meera) and the offer *Within band*.
5. Repeat with a proposed base of ₹45,00,000: the offer is *Outside band*, and waits for **Rohan**.
6. Open **Requisitions** → the finished hire (Isha Nair): the background check from a *Test background check vendor*.
7. **Reference data** (HR): edit a comp band, add a skill. As **Sana Qureshi** (IT): only access templates are editable, and the job-profile picker is empty because IT cannot read job profiles.
8. **People** → **Isha Nair**. Walk the tabs: Overview (sensitive details by consent), Job and pay (India fields), Emergency contacts (add one), Skills (rate one), Access (test identity provider; the off-template grant links to its approval), Payroll and payslips (UAN, ESIC, the first payslip), Consent and documents.
9. **John Carter** is a US employee: the same tabs show the US fields (SSN consent, FLSA, W-4, state tax).
10. **Onboarding**: Isha's checklist by owner, what blocks day one, the test identity provider. **Work authorization**: John's H-1B case, a countdown to his next step, *Test E-Verify*.
11. As **Arjun Rao** (employee): **My privacy**. Give consent for PAN, then withdraw it. His People entry lets him open only his own profile.
12. As **Meera Iyer** (manager): she opens Isha's profile (a report) but not John's. On a requisition she sees the pipeline but not the candidate's name.

## Live

Follow the README, then `VITE_API_MODE=live npm run dev`. Steps 1 to 5 (positions, requisitions, application, screening, interview, offer), reference data, People, contacts, skills and consent run on the real backend.

The backend has since built background check through payroll profile, and the frontend now runs the rest of this script live too -- see `docs/integration-demo-script.md` for a walkthrough that continues from here through consent, onboarding, access, payroll profile and a real first payslip (via the API directly; there is no Payroll screen yet). This file's own preview walkthrough above (steps 6-10) still describes the sample-data version of those same screens.
