-- Quality audit: sector-framework pass/fail
ALTER TABLE reports
    ADD COLUMN IF NOT EXISTS quality_pass BOOLEAN,
    ADD COLUMN IF NOT EXISTS quality_confidence REAL,
    ADD COLUMN IF NOT EXISTS quality_scope TEXT,
    ADD COLUMN IF NOT EXISTS quality_model TEXT,
    ADD COLUMN IF NOT EXISTS quality_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS quality_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS reports_quality_pass_idx
    ON reports (quality_pass);

CREATE INDEX IF NOT EXISTS reports_quality_at_idx
    ON reports (quality_at DESC NULLS LAST);
