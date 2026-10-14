-- Phase D of the agentic infrastructure (docs/agentic-infra-plan.md): the human surface and choreography.
--
--   1. Approval deadlines and escalation. Every pending approval gets a deadline (the gate's response window); when it passes, the
--      request is marked escalated and an `approval.escalated` event is emitted. Escalation only NOTIFIES the escalation role: it never
--      changes who may resolve the gate and never resolves or expires anything. Hard gates stay human.
--   2. app.notification: what the platform tells a role (a clock is due, an approval is overdue). Written only by app.notify.
--   3. Consumers: clock.due_soon, clock.overdue and approval.escalated are relayed to the `notify` queue.
--   4. app.inbox(): one list per signed-in role: approvals it may decide, agent runs waiting for its review, notifications.
--   5. Tenant controls over its workers: app.tenant_worker_controls() and app.set_worker_control().
--   6. app.platform_tenants(): the active tenants, so recurring platform timers can be started for all of them.

SET ROLE daydor_schema_owner;

-- ---------------------------------------------------------------------------
-- 1. Deadlines and escalation
-- ---------------------------------------------------------------------------
CREATE TABLE app.gate_sla (
    gate_id         text PRIMARY KEY,             -- '*' is the default for every gate without its own row
    respond_within  interval NOT NULL CHECK (respond_within > interval '0'),
    escalate_to     text NOT NULL DEFAULT 'tenant_founder' CHECK (escalate_to IN ('tenant_founder', 'tenant_hr', 'tenant_payroll', 'tenant_it'))
);
INSERT INTO app.gate_sla (gate_id, respond_within) VALUES
    ('*', interval '48 hours'),
    ('g_pay_disburse', interval '24 hours'),          -- people are waiting to be paid
    ('g_it_deprov', interval '24 hours'),             -- access of someone who has left
    ('g_cobra', interval '24 hours');                 -- a statutory notice
GRANT SELECT ON app.gate_sla TO daydor_ops, daydor_admin, external_auditor;

-- For the session's tenant: give every pending request a deadline, then escalate those past it (once). Returns how many it escalated.
CREATE FUNCTION app.sweep_approvals(p_now timestamptz DEFAULT now()) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    r record;
    n integer := 0;
BEGIN
    UPDATE public.approval_request ar
    SET deadline_at = ar.created_at + coalesce((SELECT s.respond_within FROM app.gate_sla s WHERE s.gate_id = ar.gate_type),
                                               (SELECT s.respond_within FROM app.gate_sla s WHERE s.gate_id = '*'))
    WHERE ar.tenant_id = app.tenant_id() AND ar.status = 'pending' AND ar.deadline_at IS NULL;

    FOR r IN SELECT ar.id, ar.gate_type, ar.required_approver_role, ar.deadline_at,
                    coalesce((SELECT s.escalate_to FROM app.gate_sla s WHERE s.gate_id = ar.gate_type),
                             (SELECT s.escalate_to FROM app.gate_sla s WHERE s.gate_id = '*')) AS escalate_to
             FROM public.approval_request ar
             WHERE ar.tenant_id = app.tenant_id() AND ar.status = 'pending' AND ar.escalated_at IS NULL AND ar.deadline_at <= p_now
             FOR UPDATE LOOP
        UPDATE public.approval_request SET escalated_at = p_now WHERE id = r.id;
        PERFORM app.emit_event('approval.escalated', 'approval_request', r.id,
            jsonb_build_object('approval_request_id', r.id, 'gate_id', r.gate_type, 'required_approver_role', r.required_approver_role,
                               'escalate_to', r.escalate_to, 'deadline_at', r.deadline_at,
                               'gate_label', coalesce((SELECT g.label FROM app.gate_definition g WHERE g.gate_id = r.gate_type), r.gate_type)));
        n := n + 1;
    END LOOP;
    RETURN n;
END $$;
GRANT EXECUTE ON FUNCTION app.sweep_approvals(timestamptz) TO worker_root_orchestrator, daydor_ops;

-- ---------------------------------------------------------------------------
-- 2. Notifications
-- ---------------------------------------------------------------------------
CREATE TABLE app.notification (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL DEFAULT app.tenant_id() REFERENCES public.tenant (id),
    audience_role   text NOT NULL CHECK (audience_role IN ('tenant_founder', 'tenant_hr', 'tenant_payroll', 'tenant_it', 'daydor_ops')),
    kind            text NOT NULL,
    severity        text NOT NULL CHECK (severity IN ('info', 'due_soon', 'overdue', 'escalated')),
    title           text NOT NULL,
    subject_table   text,
    subject_id      uuid,
    detail          jsonb NOT NULL DEFAULT '{}',
    dedupe_key      text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    dismissed_at    timestamptz,
    dismissed_by    uuid,
    UNIQUE (tenant_id, dedupe_key),
    CHECK ((dismissed_at IS NULL) = (dismissed_by IS NULL))
);
CREATE INDEX notification_open_idx ON app.notification (tenant_id, audience_role) WHERE dismissed_at IS NULL;
ALTER TABLE app.notification ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.notification FORCE ROW LEVEL SECURITY;
-- A role reads the notifications addressed to it; the founder and Daydor's own staff read all of the tenant's.
CREATE POLICY read_own ON app.notification FOR SELECT
    USING (tenant_id = app.tenant_id()
           AND (audience_role = app.current_app_role()
                OR app.current_app_role() IN ('tenant_founder', 'daydor_ops', 'daydor_admin', 'external_auditor')));
CREATE POLICY write_tenant ON app.notification FOR INSERT WITH CHECK (tenant_id = app.tenant_id());
CREATE POLICY dismiss_tenant ON app.notification FOR UPDATE USING (tenant_id = app.tenant_id()) WITH CHECK (tenant_id = app.tenant_id());
GRANT SELECT ON app.notification TO daydor_ops, daydor_admin, external_auditor, tenant_founder, tenant_hr, tenant_payroll, tenant_it;

CREATE FUNCTION app.notify(p_audience text, p_kind text, p_severity text, p_title text, p_subject_table text, p_subject_id uuid,
                           p_detail jsonb, p_dedupe text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
DECLARE
    v_id uuid := gen_random_uuid();
BEGIN
    -- No RETURNING and no ON CONFLICT: both apply the SELECT policy, and the notifier is not the audience. A duplicate is the dedupe key at work.
    INSERT INTO app.notification (id, audience_role, kind, severity, title, subject_table, subject_id, detail, dedupe_key)
    VALUES (v_id, p_audience, p_kind, p_severity, left(p_title, 300), p_subject_table, p_subject_id, coalesce(p_detail, '{}'), p_dedupe);
    RETURN v_id;
EXCEPTION WHEN unique_violation THEN
    RETURN NULL;
END $$;
GRANT EXECUTE ON FUNCTION app.notify(text, text, text, text, text, uuid, jsonb, text) TO worker_root_orchestrator;

-- The audience dismisses it (the founder may dismiss anyone's in the tenant). Dismissing is a person's act, so a user must be signed in.
CREATE FUNCTION app.dismiss_notification(p_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    IF app.user_id() IS NULL THEN
        RAISE EXCEPTION 'dismissing a notification needs a signed-in user' USING ERRCODE = 'insufficient_privilege';
    END IF;
    UPDATE app.notification SET dismissed_at = now(), dismissed_by = app.user_id()
    WHERE id = p_id AND tenant_id = app.tenant_id() AND dismissed_at IS NULL
      AND (audience_role = app.current_app_role() OR app.current_app_role() = 'tenant_founder');
    IF NOT FOUND THEN
        RAISE EXCEPTION 'notification % not found', p_id USING ERRCODE = 'no_data_found';
    END IF;
END $$;
GRANT EXECUTE ON FUNCTION app.dismiss_notification(uuid) TO tenant_founder, tenant_hr, tenant_payroll, tenant_it, daydor_ops;

-- ---------------------------------------------------------------------------
-- 3. Consumers
-- ---------------------------------------------------------------------------
INSERT INTO app.subscription (topic, queue, kind) VALUES
    ('clock.due_soon', 'notify', 'notify.event'),
    ('clock.overdue', 'notify', 'notify.event'),
    ('approval.escalated', 'notify', 'notify.event')
ON CONFLICT (topic, queue, kind) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 4. The inbox
-- ---------------------------------------------------------------------------
-- Approvals the caller's role may decide, agent runs waiting for review by the worker's owner (the founder sees all), and open
-- notifications for the role. Most urgent first. Nothing here lets anyone do anything: acting on an item is the gate's or the run's own function.
CREATE FUNCTION app.inbox()
RETURNS TABLE (kind text, id uuid, state text, title text, subject_table text, subject_id uuid, since timestamptz, due_at timestamptz,
               detail jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    WITH me AS (SELECT app.current_app_role() AS role, app.user_id() AS uid, app.tenant_id() AS tenant),
    items AS (
        SELECT 'approval'::text AS kind, ar.id,
               CASE WHEN ar.escalated_at IS NOT NULL THEN 'escalated'
                    WHEN ar.deadline_at IS NOT NULL AND ar.deadline_at < now() THEN 'overdue' ELSE 'waiting' END AS state,
               coalesce(gd.label, ar.gate_type) AS title, ar.subject_table, ar.subject_id, ar.created_at AS since, ar.deadline_at AS due_at,
               jsonb_build_object('gate', ar.gate_type, 'requested_by_me', me.uid IS NOT NULL AND ar.requested_by_user_id = me.uid,
                                  'worker', r.worker_name, 'proposal', ap.id) AS detail
        FROM me, public.approval_request ar
        LEFT JOIN app.gate_definition gd ON gd.gate_id = ar.gate_type
        LEFT JOIN public.agent_task_run r ON ar.subject_table = 'agent_task_run' AND r.id = ar.subject_id
        LEFT JOIN app.agent_proposal ap ON ap.run_id = r.id
        WHERE ar.tenant_id = me.tenant AND ar.status = 'pending'
          AND me.role = ANY (app.approval_allowed_roles(ar.gate_type, ar.required_approver_role))
        UNION ALL
        SELECT 'review', r.id, 'review', r.worker_name || ' finished a task and is waiting for your review', 'agent_task_run', r.id,
               r.started_at, NULL::timestamptz,
               jsonb_build_object('worker', r.worker_name, 'proposal', ap.id, 'proposal_status', ap.status)
        FROM me, public.agent_task_run r
        JOIN app.worker_definition d ON d.worker = r.worker_name
        LEFT JOIN app.agent_proposal ap ON ap.run_id = r.id
        WHERE r.tenant_id = me.tenant AND r.status = 'review_pending'
          AND (me.role = 'tenant_founder' OR me.role = CASE d.owner WHEN 'hr' THEN 'tenant_hr' WHEN 'payroll' THEN 'tenant_payroll'
                                                                    WHEN 'it' THEN 'tenant_it' WHEN 'founder' THEN 'tenant_founder'
                                                                    WHEN 'ops' THEN 'daydor_ops' END)
        UNION ALL
        SELECT 'notification', n.id, n.severity, n.title, n.subject_table, n.subject_id, n.created_at, NULL::timestamptz, n.detail
        FROM me, app.notification n
        WHERE n.tenant_id = me.tenant AND n.dismissed_at IS NULL AND n.audience_role = me.role
    )
    SELECT i.kind, i.id, i.state, i.title, i.subject_table, i.subject_id, i.since, i.due_at, i.detail FROM items i
    ORDER BY CASE i.state WHEN 'escalated' THEN 0 WHEN 'overdue' THEN 1 WHEN 'due_soon' THEN 2 WHEN 'review' THEN 3 ELSE 4 END, i.since
$$;
GRANT EXECUTE ON FUNCTION app.inbox() TO tenant_founder, tenant_hr, tenant_payroll, tenant_it, daydor_ops;

-- ---------------------------------------------------------------------------
-- 5. A tenant's controls over its workers
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.tenant_worker_controls()
RETURNS TABLE (worker text, home_domain text, kind text, effect text, owner text, default_autonomy text, tenant_autonomy text,
               effective_autonomy text, enabled boolean, tenant_enabled boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    SELECT d.worker, d.home_domain, d.kind, d.effect, d.owner, d.autonomy, p.autonomy, app.worker_effective_autonomy(d.worker),
           d.enabled, coalesce(p.enabled, true)
    FROM app.worker_definition d
    LEFT JOIN app.worker_tenant_policy p ON p.worker = d.worker AND p.tenant_id = app.tenant_id()
    WHERE NOT d.platform_actor
    ORDER BY d.home_domain, d.worker
$$;

-- Founder or HR. A tenant can only be more careful than the default (the table's guard rejects anything else) and cannot touch a
-- platform actor. NULL autonomy means the worker's default.
CREATE FUNCTION app.set_worker_control(p_worker text, p_autonomy text, p_enabled boolean) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
BEGIN
    IF app.current_app_role() NOT IN ('tenant_founder', 'tenant_hr') THEN
        RAISE EXCEPTION 'only the founder or HR change how workers act' USING ERRCODE = 'insufficient_privilege';
    END IF;
    UPDATE app.worker_tenant_policy SET autonomy = p_autonomy, enabled = p_enabled
    WHERE tenant_id = app.tenant_id() AND worker = p_worker;
    IF NOT FOUND THEN
        INSERT INTO app.worker_tenant_policy (worker, autonomy, enabled) VALUES (p_worker, p_autonomy, p_enabled);
    END IF;
    PERFORM app.emit_event('worker.policy_changed', NULL, NULL,
        jsonb_build_object('worker', p_worker, 'autonomy', p_autonomy, 'enabled', p_enabled, 'by', app.user_id()));
    RETURN app.worker_effective_autonomy(p_worker);
END $$;
GRANT EXECUTE ON FUNCTION app.tenant_worker_controls() TO tenant_founder, tenant_hr, daydor_ops;
GRANT EXECUTE ON FUNCTION app.set_worker_control(text, text, boolean) TO tenant_founder, tenant_hr;

-- ---------------------------------------------------------------------------
-- 6. Active tenants, for recurring platform timers. Owned by daydor_system: it has to see every tenant.
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.platform_tenants() RETURNS SETOF uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public, pg_temp AS $$
    SELECT id FROM public.tenant WHERE status = 'active' ORDER BY created_at
$$;

RESET ROLE;
GRANT SELECT (id, status, created_at) ON public.tenant TO daydor_system;
ALTER FUNCTION app.platform_tenants() OWNER TO daydor_system;
GRANT EXECUTE ON FUNCTION app.platform_tenants() TO daydor_worker, daydor_ops, daydor_admin;
