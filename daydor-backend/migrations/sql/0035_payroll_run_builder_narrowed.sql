-- payroll-run-builder's scope narrows (run_builder.py was split across its workers, Oct 13 2026).
-- 0025 and 0028 are regenerated in place for fresh installs; this is the incremental for databases that
-- already ran them: it revokes what the combined scope granted and no longer applies, and updates the
-- builder's registry row. Generated once from the difference between the old and new 0028; safe to replay
-- on a fresh install, where there is nothing to revoke.
SET ROLE daydor_schema_owner;

REVOKE SELECT (benefit_plan_id, carrier_sent_at, coverage_tier, created_at, effective_from, effective_to, employee_cost, employee_id, id, life_event_id, tenant_id, updated_at) ON public.benefit_election FROM worker_payroll_run_builder;
REVOKE SELECT (amount_or_pct, created_at, effective_from, effective_to, employee_id, id, issuing_authority, order_type, priority, tenant_id, updated_at) ON public.garnishment_order FROM worker_payroll_run_builder;
REVOKE SELECT (as_of, balance_days, created_at, employee_id, id, leave_policy_id, tenant_id, updated_at) ON public.leave_balance FROM worker_payroll_run_builder;
REVOKE SELECT (created_at, employee_id, esic_ip_number, id, pay_frequency, payment_method, reciprocity_agreement_flag, state_registration_status, tax_state, tenant_id, uan_number, updated_at, w4_elections, work_state) ON public.payroll_profile FROM worker_payroll_run_builder;
REVOKE INSERT (employee_id, employment_record_id, issued_at, payroll_run_id, retention_class) ON public.payslip FROM worker_payroll_run_builder;
REVOKE UPDATE (employee_id, employment_record_id, issued_at, payroll_run_id, retention_class) ON public.payslip FROM worker_payroll_run_builder;
REVOKE SELECT (created_at, effective_from, effective_to, id, monthly_amount, slab_max, slab_min, state_code, updated_at) ON public.pt_slab_rule FROM worker_payroll_run_builder;
REVOKE SELECT (created_at, effective_from, effective_to, employee_rate, employer_rate, id, jurisdiction_code, scheme, updated_at, wage_ceiling) ON public.statutory_rate_rule FROM worker_payroll_run_builder;
REVOKE SELECT (approved_by_user_id, created_at, employee_id, id, overtime_hours, period_end, period_start, regular_hours, status, tenant_id, updated_at) ON public.timecard FROM worker_payroll_run_builder;

-- worker_definition is immutable at runtime except `enabled`; a migration lifts that for one statement.
ALTER TABLE app.worker_definition DISABLE TRIGGER worker_definition_guard;
UPDATE app.worker_definition SET reads = ARRAY['employee', 'employment_record', 'legal_entity', 'payslip']::text[], writes = ARRAY['gratuity_accrual_balance', 'payroll_run', 'payslip_line']::text[], flags = ARRAY['jurisdiction-packs']::text[], extra_scope = CAST('{"reads": ["employee", "employment_record", "legal_entity", "payslip"], "why": "Persists what the calculators computed (payroll/run_builder.py persist_payroll_run): lists the run''s employees, reads the current employment record and legal entity, and writes payslip_line, which cannot exist before the payslip does (finding 17). It reads payslip only to return an existing run. The computation reads (rates, slabs, garnishment orders, payroll_profile) belong to the three calculator workers; payroll_run.disbursed_at stays with direct-deposit-disburser.", "writes": ["payslip_line"]}' AS jsonb) WHERE worker = 'payroll-run-builder';
ALTER TABLE app.worker_definition ENABLE TRIGGER worker_definition_guard;

RESET ROLE;
