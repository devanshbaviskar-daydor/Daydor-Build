-- Postgres job queue, transactional outbox, timers and business-day calendars (ADR-001).
--
-- Delivery is at-least-once: a job can run again after a crash or an expired lease, so every
-- handler must be idempotent. App roles and agents only reach these tables through the
-- functions below; the dispatcher runs as daydor_worker.

SET ROLE daydor_schema_owner;

CREATE TABLE app.job (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid,                                   -- null for platform jobs
    queue            text NOT NULL,
    kind             text NOT NULL,
    payload          jsonb NOT NULL DEFAULT '{}',
    idempotency_key  text,
    status           text NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'running', 'succeeded', 'dead', 'cancelled')),
    priority         integer NOT NULL DEFAULT 100,           -- lower runs first
    attempts         integer NOT NULL DEFAULT 0,
    max_attempts     integer NOT NULL DEFAULT 5 CHECK (max_attempts >= 1),
    run_at           timestamptz NOT NULL DEFAULT now(),
    locked_by        text,
    locked_until     timestamptz,
    last_error       text,
    result           jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz
);
CREATE UNIQUE INDEX job_idempotency_idx ON app.job
    (coalesce(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX job_ready_idx ON app.job (queue, priority, run_at) WHERE status = 'queued';
CREATE INDEX job_lease_idx ON app.job (queue, locked_until) WHERE status = 'running';
CREATE TRIGGER job_touch BEFORE UPDATE ON app.job FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();

-- Events written in the same transaction as the business change, relayed to jobs afterwards.
CREATE TABLE app.outbox (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id        uuid,
    topic            text NOT NULL,
    subject_table    text,
    subject_id       uuid,
    payload          jsonb NOT NULL DEFAULT '{}',
    actor_role       text NOT NULL DEFAULT app.current_app_role(),
    created_at       timestamptz NOT NULL DEFAULT now(),
    published_at     timestamptz
);
CREATE INDEX outbox_unpublished_idx ON app.outbox (id) WHERE published_at IS NULL;

-- Which queue/kind handles each topic. Rows, so routing changes need no deploy.
CREATE TABLE app.subscription (
    topic   text NOT NULL,
    queue   text NOT NULL,
    kind    text NOT NULL,
    PRIMARY KEY (topic, queue, kind)
);

-- Due-dated wake-ups: statutory clocks, expiries, deadlines and reminders.
CREATE TABLE app.timer (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid,
    timer_key   text NOT NULL,                     -- e.g. 'i9:section2:<employee_id>'
    queue       text NOT NULL,
    kind        text NOT NULL,
    payload     jsonb NOT NULL DEFAULT '{}',
    fire_at     timestamptz NOT NULL,
    status      text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'fired', 'cancelled')),
    job_id      uuid REFERENCES app.job(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX timer_key_idx ON app.timer
    (coalesce(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), timer_key);
CREATE INDEX timer_due_idx ON app.timer (fire_at) WHERE status = 'pending';
CREATE TRIGGER timer_touch BEFORE UPDATE ON app.timer FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();

-- Holiday calendars per jurisdiction ('US-FED', 'IN-KA', ...). Weekends are always non-working.
CREATE TABLE app.holiday (
    calendar  text NOT NULL,
    day       date NOT NULL,
    name      text NOT NULL,
    PRIMARY KEY (calendar, day)
);

-- ---------------------------------------------------------------------------
-- Business days
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.is_business_day(d date, cal text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS $$
    SELECT extract(isodow FROM d) < 6
       AND NOT EXISTS (SELECT 1 FROM app.holiday h WHERE h.calendar = cal AND h.day = d)
$$;

-- The date n business days after start (start itself is day 0). Used for statutory clocks such
-- as the I-9 Section 2 deadline (3 business days after the first day of work).
CREATE FUNCTION app.add_business_days(start date, n integer, cal text) RETURNS date
LANGUAGE plpgsql STABLE AS $$
DECLARE
    d date := start;
    left_ integer := n;
BEGIN
    IF n < 0 THEN RAISE EXCEPTION 'n must be >= 0'; END IF;
    WHILE left_ > 0 LOOP
        d := d + 1;
        IF app.is_business_day(d, cal) THEN left_ := left_ - 1; END IF;
    END LOOP;
    RETURN d;
END $$;

-- ---------------------------------------------------------------------------
-- Producer API (app roles and agents). Tenant always comes from the session.
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.enqueue(p_queue text, p_kind text, p_payload jsonb DEFAULT '{}',
                            p_idempotency_key text DEFAULT NULL, p_run_at timestamptz DEFAULT now(),
                            p_max_attempts integer DEFAULT 5, p_priority integer DEFAULT 100)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO app.job (tenant_id, queue, kind, payload, idempotency_key, run_at, max_attempts, priority)
    VALUES (app.tenant_id(), p_queue, p_kind, p_payload, p_idempotency_key, p_run_at, p_max_attempts, p_priority)
    ON CONFLICT DO NOTHING
    RETURNING id INTO v_id;
    IF v_id IS NULL THEN   -- duplicate idempotency key: return the existing job
        SELECT id INTO v_id FROM app.job
        WHERE coalesce(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)
              = coalesce(app.tenant_id(), '00000000-0000-0000-0000-000000000000'::uuid)
          AND idempotency_key = p_idempotency_key;
    END IF;
    RETURN v_id;
END $$;

CREATE FUNCTION app.emit_event(p_topic text, p_subject_table text DEFAULT NULL,
                               p_subject_id uuid DEFAULT NULL, p_payload jsonb DEFAULT '{}')
RETURNS bigint
LANGUAGE sql SECURITY DEFINER SET search_path = app, pg_temp AS $$
    INSERT INTO app.outbox (tenant_id, topic, subject_table, subject_id, payload, actor_role)
    VALUES (app.tenant_id(), p_topic, p_subject_table, p_subject_id, p_payload, app.current_app_role())
    RETURNING id
$$;

-- Creates or reschedules a pending timer. Rescheduling a fired or cancelled timer is a no-op.
CREATE FUNCTION app.schedule_timer(p_timer_key text, p_queue text, p_kind text, p_fire_at timestamptz,
                                   p_payload jsonb DEFAULT '{}')
RETURNS uuid
LANGUAGE sql SECURITY DEFINER SET search_path = app, pg_temp AS $$
    INSERT INTO app.timer (tenant_id, timer_key, queue, kind, payload, fire_at)
    VALUES (app.tenant_id(), p_timer_key, p_queue, p_kind, p_payload, p_fire_at)
    ON CONFLICT (coalesce(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), timer_key)
    DO UPDATE SET fire_at = EXCLUDED.fire_at, payload = EXCLUDED.payload
        WHERE app.timer.status = 'pending'
    RETURNING id
$$;

CREATE FUNCTION app.cancel_timer(p_timer_key text) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = app, pg_temp AS $$
    WITH c AS (
        UPDATE app.timer SET status = 'cancelled'
        WHERE coalesce(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)
              = coalesce(app.tenant_id(), '00000000-0000-0000-0000-000000000000'::uuid)
          AND timer_key = p_timer_key AND status = 'pending'
        RETURNING 1)
    SELECT EXISTS (SELECT 1 FROM c)
$$;

-- ---------------------------------------------------------------------------
-- Dispatcher API (daydor_worker only)
-- ---------------------------------------------------------------------------
CREATE FUNCTION app.claim_jobs(p_queue text, p_worker text, p_limit integer DEFAULT 10,
                               p_lease interval DEFAULT '5 minutes')
RETURNS SETOF app.job
LANGUAGE sql SECURITY DEFINER SET search_path = app, pg_temp AS $$
    UPDATE app.job j
    SET status = 'running', attempts = j.attempts + 1, locked_by = p_worker,
        locked_until = now() + p_lease
    FROM (
        SELECT id FROM app.job
        WHERE queue = p_queue
          AND ((status = 'queued' AND run_at <= now())
               OR (status = 'running' AND locked_until < now()))   -- reclaim expired leases
        ORDER BY priority, run_at
        LIMIT p_limit
        FOR UPDATE SKIP LOCKED
    ) ready
    WHERE j.id = ready.id
    RETURNING j.*
$$;

CREATE FUNCTION app.complete_job(p_job uuid, p_worker text, p_result jsonb DEFAULT NULL)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
BEGIN
    UPDATE app.job SET status = 'succeeded', result = p_result, finished_at = now(),
                       locked_by = NULL, locked_until = NULL
    WHERE id = p_job AND status = 'running' AND locked_by = p_worker;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'lease lost for job %', p_job USING ERRCODE = 'lock_not_available';
    END IF;
END $$;

-- Backoff: 10s, 20s, 40s ... capped at 1 hour. After max_attempts the job is dead-lettered.
CREATE FUNCTION app.fail_job(p_job uuid, p_worker text, p_error text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    v_status text;
BEGIN
    UPDATE app.job
    SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
        run_at = now() + least(interval '1 hour', interval '10 seconds' * power(2, attempts - 1)),
        last_error = p_error, locked_by = NULL, locked_until = NULL,
        finished_at = CASE WHEN attempts >= max_attempts THEN now() END
    WHERE id = p_job AND status = 'running' AND locked_by = p_worker
    RETURNING status INTO v_status;
    IF v_status IS NULL THEN
        RAISE EXCEPTION 'lease lost for job %', p_job USING ERRCODE = 'lock_not_available';
    END IF;
    RETURN v_status;
END $$;

CREATE FUNCTION app.retry_dead_job(p_job uuid) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = app, pg_temp AS $$
    UPDATE app.job SET status = 'queued', attempts = 0, run_at = now(), finished_at = NULL
    WHERE id = p_job AND status = 'dead'
$$;

-- Moves unpublished outbox events into jobs for every matching subscription.
CREATE FUNCTION app.relay_outbox(p_limit integer DEFAULT 100) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    e record;
    n integer := 0;
BEGIN
    FOR e IN SELECT * FROM app.outbox WHERE published_at IS NULL ORDER BY id
             LIMIT p_limit FOR UPDATE SKIP LOCKED LOOP
        INSERT INTO app.job (tenant_id, queue, kind, payload, idempotency_key)
        SELECT e.tenant_id, s.queue, s.kind,
               jsonb_build_object('event_id', e.id, 'topic', e.topic, 'subject_table', e.subject_table,
                                  'subject_id', e.subject_id, 'data', e.payload),
               format('outbox:%s:%s:%s', e.id, s.queue, s.kind)
        FROM app.subscription s WHERE s.topic = e.topic
        ON CONFLICT DO NOTHING;
        UPDATE app.outbox SET published_at = now() WHERE id = e.id;
        n := n + 1;
    END LOOP;
    RETURN n;
END $$;

-- Turns due timers into jobs.
CREATE FUNCTION app.fire_due_timers(p_limit integer DEFAULT 100) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE
    t record;
    v_job uuid;
    n integer := 0;
BEGIN
    FOR t IN SELECT * FROM app.timer WHERE status = 'pending' AND fire_at <= now()
             ORDER BY fire_at LIMIT p_limit FOR UPDATE SKIP LOCKED LOOP
        INSERT INTO app.job (tenant_id, queue, kind, payload, idempotency_key)
        VALUES (t.tenant_id, t.queue, t.kind,
                t.payload || jsonb_build_object('timer_key', t.timer_key, 'fire_at', t.fire_at),
                'timer:' || t.id)
        ON CONFLICT DO NOTHING
        RETURNING id INTO v_job;
        UPDATE app.timer SET status = 'fired', job_id = v_job WHERE id = t.id;
        n := n + 1;
    END LOOP;
    RETURN n;
END $$;

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------
GRANT EXECUTE ON FUNCTION app.enqueue(text, text, jsonb, text, timestamptz, integer, integer),
    app.emit_event(text, text, uuid, jsonb),
    app.schedule_timer(text, text, text, timestamptz, jsonb),
    app.cancel_timer(text),
    app.is_business_day(date, text), app.add_business_days(date, integer, text)
    TO daydor_ops, tenant_founder, tenant_hr, tenant_payroll, tenant_it, tenant_manager,
       tenant_employee, agent_runtime, daydor_worker;

GRANT EXECUTE ON FUNCTION app.claim_jobs(text, text, integer, interval),
    app.complete_job(uuid, text, jsonb), app.fail_job(uuid, text, text),
    app.relay_outbox(integer), app.fire_due_timers(integer)
    TO daydor_worker;
GRANT EXECUTE ON FUNCTION app.retry_dead_job(uuid) TO daydor_ops;
GRANT SELECT ON app.job, app.timer TO daydor_ops;     -- operational visibility
GRANT SELECT ON app.holiday TO daydor_ops, agent_runtime, daydor_worker;
GRANT SELECT, INSERT, UPDATE ON app.subscription, app.holiday TO daydor_ops;

RESET ROLE;
