-- Add missing attempts and processed_at columns to url_queue table
-- These columns were defined in 001_initial_schema.sql but not applied to database

-- Add attempts column
ALTER TABLE url_queue
ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;

-- Add processed_at column
ALTER TABLE url_queue
ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP WITH TIME ZONE;

-- Add comments for documentation
COMMENT ON COLUMN url_queue.attempts IS 'Number of processing attempts';
COMMENT ON COLUMN url_queue.processed_at IS 'When URL was successfully processed';
