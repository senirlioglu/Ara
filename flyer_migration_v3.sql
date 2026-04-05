-- ============================================================================
-- MIGRATION: Flyer Pipeline v2 → v3 (Price-Anchored Regions)
-- Run this ONCE in Supabase SQL Editor.
-- Safe to re-run (all statements are IF NOT EXISTS / IF EXISTS).
-- ============================================================================

-- 1. Add new columns to flyers table
ALTER TABLE flyers ADD COLUMN IF NOT EXISTS pdf_filename TEXT;
ALTER TABLE flyers ADD COLUMN IF NOT EXISTS page_no INTEGER DEFAULT 1;
ALTER TABLE flyers ADD COLUMN IF NOT EXISTS zoom REAL DEFAULT 3.5;

-- Backfill pdf_filename from old "filename" column
UPDATE flyers SET pdf_filename = filename
WHERE pdf_filename IS NULL AND filename IS NOT NULL;

-- 2. Create flyer_regions table (new — price-anchored product regions)
CREATE TABLE IF NOT EXISTS flyer_regions (
    region_id    SERIAL PRIMARY KEY,
    flyer_id     INTEGER NOT NULL REFERENCES flyers(flyer_id) ON DELETE CASCADE,
    price_value  TEXT,
    price_bbox   JSONB,
    x0           REAL NOT NULL,
    y0           REAL NOT NULL,
    x1           REAL NOT NULL,
    y1           REAL NOT NULL,
    region_text  TEXT,
    keys_json    JSONB DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_flyer_regions_flyer ON flyer_regions (flyer_id);

-- 3. Add region_id + candidates_json to flyer_matches (nullable — backward compat)
ALTER TABLE flyer_matches ADD COLUMN IF NOT EXISTS region_id INTEGER;
ALTER TABLE flyer_matches ADD COLUMN IF NOT EXISTS candidates_json JSONB DEFAULT '[]';

-- Add FK constraint for region_id (safe — only if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_flyer_matches_region'
          AND table_name = 'flyer_matches'
    ) THEN
        ALTER TABLE flyer_matches
            ADD CONSTRAINT fk_flyer_matches_region
            FOREIGN KEY (region_id) REFERENCES flyer_regions(region_id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_flyer_matches_region ON flyer_matches (region_id);

-- 4. Auto-update trigger for flyer_matches.updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_flyer_matches_updated ON flyer_matches;
CREATE TRIGGER trg_flyer_matches_updated
    BEFORE UPDATE ON flyer_matches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
