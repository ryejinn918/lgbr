-- Link already-collected external reports to a locked Consensus axis.
-- FnGuide documents remain the primary run_docs; this table stores only
-- supplementary external evidence and its relation to the primary view.

CREATE TABLE IF NOT EXISTS consensus_axis_external_docs (
    run_id UUID NOT NULL
        REFERENCES consensus_runs (id) ON DELETE CASCADE,
    axis_index INTEGER NOT NULL CHECK (axis_index >= 0),
    axis_label TEXT NOT NULL,
    report_id UUID NOT NULL
        REFERENCES reports (id) ON DELETE RESTRICT,
    relation TEXT NOT NULL
        CHECK (relation IN ('corroboration', 'dissent', 'supplement')),
    select_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, axis_index, report_id)
);

CREATE INDEX IF NOT EXISTS consensus_axis_external_docs_run_idx
    ON consensus_axis_external_docs (run_id, axis_index, relation);

CREATE INDEX IF NOT EXISTS consensus_axis_external_docs_report_idx
    ON consensus_axis_external_docs (report_id);
