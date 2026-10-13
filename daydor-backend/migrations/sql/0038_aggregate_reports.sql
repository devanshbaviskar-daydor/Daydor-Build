-- Finding 7: aggregate-only access (level 1 "Σ" in the model) gets a mechanism.
--
-- The model gives some roles only aggregate access to a table: Daydor ops, the founder, HR and the external auditor
-- on `self_identification` (race or ethnicity, gender, veteran and disability status: C4, special category). They get
-- no column grant, so they cannot read a row. What they may have is a count, and a count of fewer than five people can
-- identify one. So the report is a SECURITY DEFINER function that returns counts only, and a cell with fewer than
-- five people comes back with its count withheld.
--
--   * It runs as the table owner under FORCE row security, so it sees only the session's tenant (app.tenant_id()),
--     including the ops-assignment check of 0037.
--   * The minimum cell size is five and the caller cannot lower it: p_min is raised to five if it is below.
--   * It returns no totals, so a withheld cell cannot be recovered by subtraction.
--   * Only the roles whose access to the table is aggregate-only, and the eeo-report-builder worker, may call it.

SET ROLE daydor_schema_owner;

-- Workforce by job family, race or ethnicity and gender, over current employees who have a self-identification
-- record (the EEO-1 shape). employees is NULL and suppressed is true when the cell has fewer than p_min people.
CREATE FUNCTION app.eeo1_report(p_min integer DEFAULT 5)
RETURNS TABLE (job_family text, race_ethnicity text, gender text, employees integer, suppressed boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    WITH cells AS (
        SELECT jp.job_family::text AS job_family, s.race_ethnicity::text AS race_ethnicity, s.gender::text AS gender,
               count(DISTINCT e.id)::integer AS n
        FROM public.self_identification s
        JOIN public.employee e ON e.id = s.employee_id AND e.tenant_id = app.tenant_id() AND e.is_active
        JOIN public.employment_record er ON er.employee_id = e.id AND er.tenant_id = app.tenant_id()
             AND er.effective_from <= current_date AND (er.effective_to IS NULL OR er.effective_to >= current_date)
        JOIN public.job_profile jp ON jp.id = er.job_profile_id
        WHERE s.tenant_id = app.tenant_id()
        GROUP BY 1, 2, 3
    )
    SELECT c.job_family, c.race_ethnicity, c.gender,
           CASE WHEN c.n >= greatest(p_min, 5) THEN c.n END,
           c.n < greatest(p_min, 5)
    FROM cells c
    ORDER BY c.job_family, c.race_ethnicity, c.gender
$$;

GRANT EXECUTE ON FUNCTION app.eeo1_report(integer)
    TO daydor_ops, tenant_founder, tenant_hr, external_auditor, worker_eeo_report_builder;

RESET ROLE;
