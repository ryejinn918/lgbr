-- Human-readable per-crawl asset folder id (fn-dc-n20-250723-a1b2c3)
ALTER TABLE fnguide_crawls
    ADD COLUMN IF NOT EXISTS asset_id TEXT;

UPDATE fnguide_crawls
SET asset_id = concat_ws(
    '-',
    'fn',
    CASE mode
        WHEN 'datacenter' THEN 'dc'
        WHEN 'adhoc' THEN 'ad'
        ELSE 'au'
    END
    || CASE
        WHEN mode = 'datacenter' THEN concat('-n', report_limit::text)
        ELSE ''
    END,
    to_char(started_at AT TIME ZONE 'Asia/Seoul', 'YYMMDD'),
    substr(replace(id::text, '-', ''), 1, 6)
)
WHERE asset_id IS NULL;

ALTER TABLE fnguide_crawls
    ALTER COLUMN asset_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS fnguide_crawls_asset_id_uidx
    ON fnguide_crawls (asset_id);
