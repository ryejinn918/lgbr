-- Remove unused MCP SQL exploration surface; keep pg_trgm indexes from 031.

DROP VIEW IF EXISTS mcp_reports;

DO $$
DECLARE
    r record;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lgbr_mcp_ro') THEN
        FOR r IN
            SELECT m.rolname AS member_name
            FROM pg_auth_members am
            JOIN pg_roles m ON m.oid = am.member
            JOIN pg_roles g ON g.oid = am.roleid
            WHERE g.rolname = 'lgbr_mcp_ro'
        LOOP
            EXECUTE format('REVOKE lgbr_mcp_ro FROM %I', r.member_name);
        END LOOP;
        DROP ROLE lgbr_mcp_ro;
    END IF;
END
$$;
