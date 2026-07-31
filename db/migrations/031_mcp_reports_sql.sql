-- MCP read-only exploration: flattened view, RO role, pg_trgm indexes.
-- Security boundary is Postgres GRANT (not app SQL table allowlists).

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE VIEW mcp_reports AS
SELECT
    r.id,
    r.source,
    r.source_key,
    r.title,
    COALESCE(r.status, 'listed') AS status,
    (r.file_path IS NOT NULL) AS has_file,
    NULLIF(BTRIM(r.attrs->>'provider'), '') AS provider,
    COALESCE(r.attrs->'themes', '[]'::jsonb) AS themes,
    r.published_at,
    r.page_count,
    CASE
        WHEN r.quality_pass IS TRUE THEN 'pass'
        WHEN r.quality_pass IS FALSE THEN 'fail'
        WHEN r.status = 'downloaded' AND r.file_path IS NOT NULL THEN 'pending'
        ELSE 'unauditable'
    END AS quality,
    r.quality_pass,
    r.quality_scope,
    r.quality_at,
    NULLIF(BTRIM(r.quality_json->>'short_title'), '') AS short_title,
    NULLIF(
        BTRIM(
            COALESCE(
                r.quality_json->>'summary',
                r.quality_json->>'framework_summary'
            )
        ),
        ''
    ) AS summary,
    NULLIF(BTRIM(r.quality_json->>'topic'), '') AS topic,
    NULLIF(BTRIM(r.quality_json->>'framework_summary'), '') AS framework_summary,
    CASE
        WHEN lower(r.source) = 'fnguide' THEN 'sell_side'
        ELSE 'summary'
    END AS audit_kind,
    CASE
        WHEN r.attrs->>'url' ~* '^https?://' THEN r.attrs->>'url'
        ELSE NULL
    END AS url,
    r.last_seen_at
FROM reports r;

COMMENT ON VIEW mcp_reports IS
    'MCP collect SQL surface: metadata + summaries + original web url; no PDF paths.';

-- Text indexes (base table expression indexes used via view queries)
CREATE INDEX IF NOT EXISTS reports_published_at_idx
    ON reports (published_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS reports_source_published_idx
    ON reports (source, published_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS reports_quality_pass_published_idx
    ON reports (quality_pass, published_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS reports_title_trgm_idx
    ON reports USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS reports_provider_trgm_idx
    ON reports USING gin ((attrs->>'provider') gin_trgm_ops);

CREATE INDEX IF NOT EXISTS reports_qj_short_title_trgm_idx
    ON reports USING gin ((quality_json->>'short_title') gin_trgm_ops);

CREATE INDEX IF NOT EXISTS reports_qj_summary_trgm_idx
    ON reports USING gin ((quality_json->>'summary') gin_trgm_ops);

CREATE INDEX IF NOT EXISTS reports_qj_framework_trgm_idx
    ON reports USING gin ((quality_json->>'framework_summary') gin_trgm_ops);

CREATE INDEX IF NOT EXISTS reports_themes_gin_idx
    ON reports USING gin ((attrs->'themes'));

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lgbr_mcp_ro') THEN
        CREATE ROLE lgbr_mcp_ro NOLOGIN;
    END IF;
END
$$;

ALTER ROLE lgbr_mcp_ro SET default_transaction_read_only = on;
ALTER ROLE lgbr_mcp_ro SET statement_timeout = '3s';

REVOKE ALL ON TABLE mcp_reports FROM PUBLIC;
GRANT SELECT ON TABLE mcp_reports TO lgbr_mcp_ro;

-- Allow the migration/app role to SET ROLE lgbr_mcp_ro
GRANT lgbr_mcp_ro TO CURRENT_USER;
