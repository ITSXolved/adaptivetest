-- 3-Tier Cache System - Database Migration SQL
-- Run this in Supabase SQL Editor

-- =====================================================
-- CREATE QUESTION_POOLS TABLE (Tier 2 Cache Metadata)
-- =====================================================

CREATE TABLE IF NOT EXISTS question_pools (
  id VARCHAR PRIMARY KEY,  -- Format: "level_level_id" (e.g., "topic_uuid")
  level VARCHAR NOT NULL,  -- 'topic', 'chapter', 'subject', 'class', 'exam'
  level_id UUID NOT NULL,  -- UUID of the level
  attribute_count INT DEFAULT 0,
  attributes JSONB DEFAULT '[]',  -- Array of attribute objects
  total_questions INT DEFAULT 0,
  metadata JSONB DEFAULT '{}',  -- Additional metadata
  cached_at TIMESTAMP DEFAULT NOW(),
  expires_at VARCHAR,  -- Unix timestamp as string
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_question_pools_level ON question_pools(level);
CREATE INDEX IF NOT EXISTS idx_question_pools_level_id ON question_pools(level_id);
CREATE INDEX IF NOT EXISTS idx_question_pools_cached_at ON question_pools(cached_at);
CREATE INDEX IF NOT EXISTS idx_question_pools_expires_at ON question_pools(expires_at);

-- Composite index for common queries
CREATE INDEX IF NOT EXISTS idx_question_pools_level_level_id ON question_pools(level, level_id);

-- =====================================================
-- UPDATE QUESTIONS TABLE (Add external API fields)
-- =====================================================

-- Add new columns for external API metadata
ALTER TABLE questions
  ADD COLUMN IF NOT EXISTS guessing DECIMAL DEFAULT 0.25;

ALTER TABLE questions
  ADD COLUMN IF NOT EXISTS topic_id UUID;

ALTER TABLE questions
  ADD COLUMN IF NOT EXISTS chapter_id UUID;

ALTER TABLE questions
  ADD COLUMN IF NOT EXISTS subject_id UUID;

ALTER TABLE questions
  ADD COLUMN IF NOT EXISTS class_id UUID;

ALTER TABLE questions
  ADD COLUMN IF NOT EXISTS exam_id UUID;

-- Add indexes for hierarchical queries
CREATE INDEX IF NOT EXISTS idx_questions_topic_id ON questions(topic_id);
CREATE INDEX IF NOT EXISTS idx_questions_chapter_id ON questions(chapter_id);
CREATE INDEX IF NOT EXISTS idx_questions_subject_id ON questions(subject_id);
CREATE INDEX IF NOT EXISTS idx_questions_class_id ON questions(class_id);
CREATE INDEX IF NOT EXISTS idx_questions_exam_id ON questions(exam_id);

-- =====================================================
-- CLEAN UP EXPIRED CACHE FUNCTION (Optional)
-- =====================================================

CREATE OR REPLACE FUNCTION cleanup_expired_question_pools()
RETURNS INTEGER AS $$
DECLARE
  deleted_count INTEGER;
BEGIN
  -- Delete pools where expires_at timestamp has passed
  DELETE FROM question_pools
  WHERE CAST(expires_at AS NUMERIC) < EXTRACT(EPOCH FROM NOW());

  GET DIAGNOSTICS deleted_count = ROW_COUNT;

  RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Optional: Create a cron job to run cleanup daily
-- (Requires pg_cron extension - may not be available in Supabase free tier)
-- SELECT cron.schedule('cleanup-expired-pools', '0 2 * * *', 'SELECT cleanup_expired_question_pools()');

-- =====================================================
-- VIEW FOR CACHE STATISTICS
-- =====================================================

CREATE OR REPLACE VIEW v_cache_statistics AS
SELECT
  COUNT(*) as total_pools,
  SUM(total_questions) as total_questions_cached,
  COUNT(CASE WHEN CAST(expires_at AS NUMERIC) < EXTRACT(EPOCH FROM NOW()) THEN 1 END) as expired_pools,
  COUNT(CASE WHEN level = 'topic' THEN 1 END) as topic_pools,
  COUNT(CASE WHEN level = 'chapter' THEN 1 END) as chapter_pools,
  COUNT(CASE WHEN level = 'subject' THEN 1 END) as subject_pools,
  COUNT(CASE WHEN level = 'class' THEN 1 END) as class_pools,
  COUNT(CASE WHEN level = 'exam' THEN 1 END) as exam_pools,
  AVG(total_questions)::DECIMAL(10,2) as avg_questions_per_pool,
  MAX(cached_at) as last_cache_update
FROM question_pools;

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Check if tables were created successfully
SELECT
  table_name,
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'public'
  AND table_name IN ('question_pools', 'questions')
ORDER BY table_name;

-- Check indexes
SELECT
  tablename,
  indexname,
  indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('question_pools', 'questions')
ORDER BY tablename, indexname;

-- View cache statistics
SELECT * FROM v_cache_statistics;

-- =====================================================
-- SAMPLE DATA INSERTION (For Testing)
-- =====================================================

-- Insert sample question pool
INSERT INTO question_pools (id, level, level_id, attribute_count, attributes, total_questions, metadata, expires_at)
VALUES (
  'topic_62ae33ad-2598-4827-9eab-9d886586c7a6',
  'topic',
  '62ae33ad-2598-4827-9eab-9d886586c7a6',
  5,
  '[
    {
      "id": "83da0723-684e-4963-b974-d405841af660",
      "name": "Solve by Factorization",
      "description": "Ability to solve quadratic equations using factorization method"
    }
  ]'::jsonb,
  8,
  '{"source": "external_api", "version": "1.0"}'::jsonb,
  (EXTRACT(EPOCH FROM NOW()) + 604800)::TEXT  -- Expires in 7 days
)
ON CONFLICT (id) DO NOTHING;

-- =====================================================
-- ROLLBACK PLAN (if needed)
-- =====================================================

-- To rollback this migration, run:
/*
DROP VIEW IF EXISTS v_cache_statistics;
DROP FUNCTION IF EXISTS cleanup_expired_question_pools();
DROP INDEX IF EXISTS idx_question_pools_level_level_id;
DROP INDEX IF EXISTS idx_question_pools_expires_at;
DROP INDEX IF EXISTS idx_question_pools_cached_at;
DROP INDEX IF EXISTS idx_question_pools_level_id;
DROP INDEX IF EXISTS idx_question_pools_level;
DROP TABLE IF EXISTS question_pools CASCADE;

-- Remove new columns from questions table
ALTER TABLE questions DROP COLUMN IF EXISTS guessing;
ALTER TABLE questions DROP COLUMN IF EXISTS topic_id;
ALTER TABLE questions DROP COLUMN IF EXISTS chapter_id;
ALTER TABLE questions DROP COLUMN IF EXISTS subject_id;
ALTER TABLE questions DROP COLUMN IF EXISTS class_id;
ALTER TABLE questions DROP COLUMN IF EXISTS exam_id;

DROP INDEX IF EXISTS idx_questions_exam_id;
DROP INDEX IF EXISTS idx_questions_class_id;
DROP INDEX IF EXISTS idx_questions_subject_id;
DROP INDEX IF EXISTS idx_questions_chapter_id;
DROP INDEX IF EXISTS idx_questions_topic_id;
*/

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================

-- Verify migration
SELECT 'Migration completed successfully!' as status;
SELECT * FROM v_cache_statistics;
