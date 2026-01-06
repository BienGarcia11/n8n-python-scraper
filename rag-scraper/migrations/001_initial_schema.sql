-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create url_queue table
CREATE TABLE IF NOT EXISTS url_queue (
  id SERIAL PRIMARY KEY,
  url TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  error_message TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for url_queue
CREATE INDEX IF NOT EXISTS idx_url_queue_status ON url_queue(status);
CREATE INDEX IF NOT EXISTS idx_url_queue_created ON url_queue(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_url_queue_attempts ON url_queue(attempts, status);

-- Create documents table
CREATE TABLE IF NOT EXISTS documents (
  id SERIAL PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT,
  content TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  total_chunks INTEGER NOT NULL,
  embedding vector(1536),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create indexes for documents
CREATE INDEX IF NOT EXISTS idx_documents_embedding 
ON documents USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 1000);
CREATE INDEX IF NOT EXISTS idx_documents_url ON documents(url);
CREATE INDEX IF NOT EXISTS idx_documents_chunk ON documents(url, chunk_index);
CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC);

-- Create function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for url_queue
DROP TRIGGER IF EXISTS update_url_queue_updated_at ON url_queue;
CREATE TRIGGER update_url_queue_updated_at
    BEFORE UPDATE ON url_queue
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE url_queue IS 'Queue of URLs to be scraped for RAG';
COMMENT ON COLUMN url_queue.id IS 'Primary key';
COMMENT ON COLUMN url_queue.url IS 'URL to scrape';
COMMENT ON COLUMN url_queue.status IS 'Current status: pending, processing, completed, failed';
COMMENT ON COLUMN url_queue.error_message IS 'Error message if scraping failed';
COMMENT ON COLUMN url_queue.attempts IS 'Number of processing attempts';
COMMENT ON COLUMN url_queue.created_at IS 'When the URL was added to queue';
COMMENT ON COLUMN url_queue.updated_at IS 'Last time the status was updated';
COMMENT ON COLUMN url_queue.processed_at IS 'When the URL was successfully processed';

COMMENT ON TABLE documents IS 'Scraped and chunked documents with embeddings for RAG';
COMMENT ON COLUMN documents.id IS 'Primary key';
COMMENT ON COLUMN documents.url IS 'Source URL';
COMMENT ON COLUMN documents.title IS 'Page title';
COMMENT ON COLUMN documents.content IS 'Text chunk content';
COMMENT ON COLUMN documents.chunk_index IS 'Index of this chunk (0-based)';
COMMENT ON COLUMN documents.total_chunks IS 'Total number of chunks for this URL';
COMMENT ON COLUMN documents.embedding IS 'OpenAI embedding vector (text-embedding-3-small)';
COMMENT ON COLUMN documents.created_at IS 'When the document was created';
