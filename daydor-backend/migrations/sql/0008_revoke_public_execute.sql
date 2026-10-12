-- Fix: functions in the app schema were executable by PUBLIC.
--
-- 0001 ran `ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC`, but
-- per-schema default privileges can only add to the global defaults, never remove from them, so
-- it had no effect. Revoke on everything that exists and change the global default for the
-- roles that create functions. Explicit GRANTs from earlier migrations are unaffected.

REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA app FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE daydor_schema_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE daydor_system REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
