-- Track every SearchReport list sighting, not only downloaded PDFs.
ALTER TABLE reports
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'listed';

ALTER TABLE reports
    ALTER COLUMN downloaded_at DROP NOT NULL;

ALTER TABLE reports
    ALTER COLUMN downloaded_at DROP DEFAULT;

ALTER TABLE reports
    ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE reports
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now();

UPDATE reports
SET status = 'downloaded',
    first_seen_at = COALESCE(first_seen_at, downloaded_at, now()),
    last_seen_at = COALESCE(last_seen_at, downloaded_at, now())
WHERE file_path IS NOT NULL
  AND (status IS NULL OR status = 'listed');

CREATE INDEX IF NOT EXISTS reports_source_status_idx
    ON reports (source, status);

CREATE INDEX IF NOT EXISTS reports_last_seen_idx
    ON reports (last_seen_at DESC);
