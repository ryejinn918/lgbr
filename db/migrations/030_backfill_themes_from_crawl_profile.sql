-- Backfill attrs.themes from crawl_profile when themes are missing/empty.
-- Does not overwrite non-empty classified themes[].

UPDATE reports
SET attrs = attrs || jsonb_build_object(
    'themes',
    jsonb_build_array(attrs->>'crawl_profile')
)
WHERE (
    NOT (attrs ? 'themes')
    OR jsonb_typeof(attrs->'themes') <> 'array'
    OR jsonb_array_length(attrs->'themes') = 0
)
AND attrs->>'crawl_profile' IS NOT NULL
AND attrs->>'crawl_profile' <> ''
AND attrs->>'crawl_profile' IN (
    'ai',
    'datacenter',
    'macroeconomy',
    'physical_ai',
    'appliance',
    'display',
    'automotive',
    'petrochemical'
);
