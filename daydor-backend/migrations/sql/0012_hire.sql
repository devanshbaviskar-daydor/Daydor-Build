-- Hire flow support.
--
-- employee.{aadhaar_ekyc_ref,pan_encrypted,ssn_encrypted,bank_account_encrypted} are modelled
-- NOT NULL, but encrypted columns carry no INSERT grant for any role (ADR-002) and consent_record
-- needs an existing employee_id to reference. So the only legal order is: create the employee row
-- first (these 4 columns start NULL), capture consent (now that employee_id exists to reference),
-- then call app.encrypt_pii to populate them -- which is also the hire flow's own step order
-- (`employee` is step 10, `consent_record` is step 12). Relaxing NOT NULL here, instead of in the
-- generated DDL, keeps this a documented, additive deviation rather than a generator change; see
-- docs/model-findings.md finding 10. Push the nullability back into the artifact once agreed.
ALTER TABLE public.employee ALTER COLUMN aadhaar_ekyc_ref DROP NOT NULL;
ALTER TABLE public.employee ALTER COLUMN pan_encrypted DROP NOT NULL;
ALTER TABLE public.employee ALTER COLUMN ssn_encrypted DROP NOT NULL;
ALTER TABLE public.employee ALTER COLUMN bank_account_encrypted DROP NOT NULL;

-- employment_record has no natural key beyond its surrogate id; one per (employee, effective
-- date) lets the writer be idempotent the same way employee.hire_event_id does.
ALTER TABLE public.employment_record ADD CONSTRAINT employment_record_employee_effective_from_key
    UNIQUE (tenant_id, employee_id, effective_from);
