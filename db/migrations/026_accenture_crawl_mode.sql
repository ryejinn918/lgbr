-- Allow Accenture US adhoc crawls (no FnGuide login; CDP hold).
ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_mode_check;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_mode_check
    CHECK (mode IN (
        'auto',
        'adhoc',
        'pwc',
        'accenture',
        'ai',
        'physical_ai',
        'appliance',
        'display',
        'automotive',
        'petrochemical'
    ));
