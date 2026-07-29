-- Default look-back for all FnGuide search profiles is 3 months.
UPDATE search_profiles
SET period_months = 3,
    updated_at = now()
WHERE period_months <> 3;
