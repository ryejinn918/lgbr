-- Bibliography / fill-only docs on consensus runs.
ALTER TABLE consensus_run_docs
    DROP CONSTRAINT IF EXISTS consensus_run_docs_role_check;

ALTER TABLE consensus_run_docs
    ADD CONSTRAINT consensus_run_docs_role_check
    CHECK (role IN ('selected', 'fill_extra', 'excluded'));
