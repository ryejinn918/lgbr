-- Allow pausing after thesis cut for human review.
ALTER TABLE consensus_runs
  DROP CONSTRAINT IF EXISTS consensus_runs_state_check;

ALTER TABLE consensus_runs
  ADD CONSTRAINT consensus_runs_state_check
  CHECK (state IN ('starting', 'active', 'stopping', 'awaiting', 'ended', 'error'));
