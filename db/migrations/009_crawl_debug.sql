-- Debug handoff: datacenter job then keep browser as adhoc+CDP
ALTER TABLE fnguide_crawls
    ADD COLUMN IF NOT EXISTS debug BOOLEAN NOT NULL DEFAULT false;
