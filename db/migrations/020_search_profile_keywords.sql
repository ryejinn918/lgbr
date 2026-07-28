-- search_profiles.keyword (TEXT) → keywords (TEXT[]) for multi-keyword search.
ALTER TABLE search_profiles
    ADD COLUMN IF NOT EXISTS keywords TEXT[];

UPDATE search_profiles
SET keywords = ARRAY[keyword]
WHERE keywords IS NULL;

ALTER TABLE search_profiles
    ALTER COLUMN keywords SET NOT NULL;

ALTER TABLE search_profiles
    DROP CONSTRAINT IF EXISTS search_profiles_keywords_nonempty;

ALTER TABLE search_profiles
    ADD CONSTRAINT search_profiles_keywords_nonempty
    CHECK (cardinality(keywords) >= 1);

ALTER TABLE search_profiles
    DROP COLUMN IF EXISTS keyword;
