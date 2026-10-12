-- The API layer's own schema. It never touches the backend's schemas.
-- identity: who can sign in, and which tenant/role/user they map to. Needed because the backend's
-- app_user rows sit behind tenant row security, so a person cannot be looked up before a tenant
-- session exists.
CREATE SCHEMA IF NOT EXISTS api;

CREATE TABLE IF NOT EXISTS api.identity (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         citext NOT NULL UNIQUE,
    display_name  text NOT NULL,
    tenant_id     uuid,                 -- null only for daydor_admin
    tenant_name   text,
    user_id       uuid,                 -- backend app_user.id; null for platform staff
    employee_id   uuid,
    role          text NOT NULL,        -- database role, e.g. tenant_hr
    is_active     boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Replays of the same command return the first response instead of acting twice.
CREATE TABLE IF NOT EXISTS api.idempotency (
    identity_id uuid NOT NULL,
    route       text NOT NULL,
    key         text NOT NULL,
    response    jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (identity_id, route, key)
);
