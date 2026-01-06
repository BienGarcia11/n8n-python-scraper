-- Fix documents table schema to match validation expectations
-- Adds missing columns that were omitted in initial setup

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS url TEXT NOT NULL,
ADD COLUMN IF NOT EXISTS title TEXT,
ADD COLUMN IF NOT EXISTS chunk_index INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_chunks INTEGER NOT NULL DEFAULT 1;

-- Create index on url column for faster lookups
CREATE INDEX IF NOT EXISTS idx_documents_url_fix 
ON documents(url);

-- Add comments for new columns
COMMENT ON COLUMN documents.url IS 'Source URL for the scraped content';
COMMENT ON COLUMN documents.title IS 'Page title extracted from HTML';
COMMENT ON COLUMN documents.chunk_index IS 'Index of this chunk (0-based)';
COMMENT ON COLUMN documents.total_chunks IS 'Total number of chunks for this URL';
