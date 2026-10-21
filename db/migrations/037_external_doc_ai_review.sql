ALTER TABLE consensus_axis_external_docs
    ADD COLUMN IF NOT EXISTS ai_confidence numeric(5, 4),
    ADD COLUMN IF NOT EXISTS ai_reason text,
    ADD COLUMN IF NOT EXISTS review_state text NOT NULL DEFAULT 'manual';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'consensus_axis_external_docs_review_state_ck'
    ) THEN
        ALTER TABLE consensus_axis_external_docs
            ADD CONSTRAINT consensus_axis_external_docs_review_state_ck
            CHECK (review_state IN ('ai_suggested', 'approved', 'rejected', 'manual'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_consensus_axis_external_docs_review
    ON consensus_axis_external_docs (run_id, axis_index, review_state);
