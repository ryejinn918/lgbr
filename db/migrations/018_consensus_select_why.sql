-- Per-report selection rationale from LLM pack select.
ALTER TABLE consensus_run_docs
    ADD COLUMN IF NOT EXISTS select_why TEXT;
