-- Consensus: prompt sets, runs (join reports via run_docs), outputs, compress artifacts.

CREATE TABLE IF NOT EXISTS consensus_prompt_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS consensus_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_set_id UUID NOT NULL
        REFERENCES consensus_prompt_sets (id) ON DELETE CASCADE,
    stage TEXT NOT NULL
        CHECK (stage IN (
            'toc',
            'local_compress',
            'report_compress',
            'consensus',
            'reduce',
            'fill_plan',
            'fill'
        )),
    system_text TEXT NOT NULL,
    user_template TEXT NOT NULL,
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (prompt_set_id, stage)
);

CREATE INDEX IF NOT EXISTS consensus_prompts_set_idx
    ON consensus_prompts (prompt_set_id);

CREATE TABLE IF NOT EXISTS consensus_doc_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL
        REFERENCES reports (id) ON DELETE RESTRICT,
    content_hash TEXT NOT NULL,
    prompt_set_id UUID NOT NULL
        REFERENCES consensus_prompt_sets (id) ON DELETE RESTRICT,
    model TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('ok', 'failed')),
    toc_found BOOLEAN,
    slice_count INTEGER,
    compress_md TEXT,
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (report_id, content_hash, prompt_set_id, model)
);

CREATE INDEX IF NOT EXISTS consensus_doc_artifacts_report_idx
    ON consensus_doc_artifacts (report_id);

CREATE INDEX IF NOT EXISTS consensus_doc_artifacts_prompt_set_idx
    ON consensus_doc_artifacts (prompt_set_id);

CREATE TABLE IF NOT EXISTS consensus_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id TEXT NOT NULL UNIQUE,
    prompt_set_id UUID NOT NULL
        REFERENCES consensus_prompt_sets (id) ON DELETE RESTRICT,
    theme TEXT NOT NULL
        CHECK (theme IN ('datacenter', 'ai', 'physical_ai')),
    question TEXT NOT NULL,
    criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
    model TEXT NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('starting', 'active', 'stopping', 'ended', 'error')),
    progress JSONB NOT NULL DEFAULT '{}'::jsonb,
    pid INTEGER,
    message TEXT,
    stop_requested_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- At most one open consensus run at a time (mirror fnguide_crawls_one_open_uidx).
CREATE UNIQUE INDEX IF NOT EXISTS consensus_runs_one_open_uidx
    ON consensus_runs ((true))
    WHERE ended_at IS NULL;

CREATE INDEX IF NOT EXISTS consensus_runs_prompt_set_idx
    ON consensus_runs (prompt_set_id);

CREATE INDEX IF NOT EXISTS consensus_runs_theme_ended_idx
    ON consensus_runs (theme, ended_at DESC)
    WHERE state = 'ended';

CREATE TABLE IF NOT EXISTS consensus_run_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL
        REFERENCES consensus_runs (id) ON DELETE CASCADE,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    level TEXT NOT NULL DEFAULT 'info'
        CHECK (level IN ('debug', 'info', 'warn', 'error')),
    stage TEXT NOT NULL DEFAULT '',
    event TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS consensus_run_events_run_idx
    ON consensus_run_events (run_id, at DESC);

CREATE INDEX IF NOT EXISTS consensus_run_events_stage_idx
    ON consensus_run_events (run_id, stage, at DESC);

CREATE TABLE IF NOT EXISTS consensus_run_docs (
    run_id UUID NOT NULL
        REFERENCES consensus_runs (id) ON DELETE CASCADE,
    report_id UUID NOT NULL
        REFERENCES reports (id) ON DELETE RESTRICT,
    role TEXT NOT NULL
        CHECK (role IN ('selected', 'excluded')),
    rank INTEGER,
    exclude_reason TEXT,
    doc_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (doc_status IN ('pending', 'ok', 'failed', 'cache_hit')),
    artifact_id UUID
        REFERENCES consensus_doc_artifacts (id) ON DELETE SET NULL,
    error TEXT,
    PRIMARY KEY (run_id, report_id)
);

CREATE INDEX IF NOT EXISTS consensus_run_docs_report_idx
    ON consensus_run_docs (report_id);

CREATE INDEX IF NOT EXISTS consensus_run_docs_role_idx
    ON consensus_run_docs (run_id, role);

CREATE TABLE IF NOT EXISTS consensus_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL
        REFERENCES consensus_runs (id) ON DELETE CASCADE,
    kind TEXT NOT NULL
        CHECK (kind IN (
            'consensus_frame',
            'filled_frame',
            'reduce_frame',
            'fill_plan'
        )),
    ordinal INTEGER NOT NULL DEFAULT 0,
    body_md TEXT,
    body_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, kind, ordinal)
);

CREATE INDEX IF NOT EXISTS consensus_outputs_run_idx
    ON consensus_outputs (run_id, kind);
