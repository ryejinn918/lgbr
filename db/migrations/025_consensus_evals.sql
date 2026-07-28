-- Consensus eval: web-search baseline vs filled_frame knowledge graphs.

CREATE TABLE IF NOT EXISTS consensus_evals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL
        REFERENCES consensus_runs (id) ON DELETE CASCADE,
    state TEXT NOT NULL
        CHECK (state IN ('pending', 'running', 'ended', 'error')),
    baseline_md TEXT,
    serp_queries JSONB NOT NULL DEFAULT '[]'::jsonb,
    serp_hits JSONB NOT NULL DEFAULT '[]'::jsonb,
    graph_ours JSONB,
    graph_baseline JSONB,
    checklist JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS consensus_evals_run_created_idx
    ON consensus_evals (run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS consensus_evals_run_state_idx
    ON consensus_evals (run_id, state);
