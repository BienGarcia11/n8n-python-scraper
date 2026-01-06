-- Add missing error_message column to url_queue table
-- This migration fixes validation endpoint errors when error_message column doesn't exist

ALTER TABLE url_queue
ADD COLUMN IF NOT EXISTS error_message TEXT;

-- Add comment for documentation
COMMENT ON COLUMN url_queue.error_message IS 'Error message if scraping failed';
