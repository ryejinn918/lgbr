-- Allow PwC adhoc crawls (no FnGuide login; CDP hold for analysis / later automation).
ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_mode_check;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_mode_check
    CHECK (mode IN (
        'auto',
        'adhoc',
        'pwc',
        'ai',
        'physical_ai',
        'appliance',
        'display',
        'automotive',
        'petrochemical'
    ));
