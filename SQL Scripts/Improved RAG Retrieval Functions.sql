-- ============================================
-- IMPROVED RAG SYSTEM - SQL FUNCTIONS
-- Run these in Supabase SQL Editor
-- ============================================

-- 1. DROP OLD FUNCTIONS (if they exist)
DROP FUNCTION IF EXISTS match_documents(vector(1536), float, int);
DROP FUNCTION IF EXISTS match_cache(vector(1536), float);

-- ============================================
-- 2. IMPROVED DOCUMENT SEARCH with HYBRID
-- ============================================
CREATE OR REPLACE FUNCTION match_documents_hybrid(
  query_embedding vector(1536),
  query_text text,
  match_threshold float DEFAULT 0.5,
  match_count int DEFAULT 10
)
RETURNS TABLE (
  id uuid,
  content text,
  metadata jsonb,
  similarity float
)
LANGUAGE plpgsql
AS $function$
BEGIN
  RETURN QUERY
  SELECT 
    d.id,
    d.content,
    d.metadata,
    (1 - (d.embedding <=> query_embedding)) as similarity
  FROM documents d
  WHERE 
    (1 - (d.embedding <=> query_embedding)) > match_threshold
  ORDER BY 
    (
      (1 - (d.embedding <=> query_embedding)) * 0.8 +
      COALESCE(
        ts_rank(
          to_tsvector('english', d.content), 
          plainto_tsquery('english', query_text)
        ) * 0.2,
        0
      )
    ) DESC
  LIMIT match_count;
END;
$function$;

-- ============================================
-- 3. SIMPLE VECTOR-ONLY SEARCH (Backup/Fallback)
-- ============================================
CREATE OR REPLACE FUNCTION match_documents_simple(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.5,
  match_count int DEFAULT 10
)
RETURNS TABLE (
  id uuid,
  content text,
  metadata jsonb,
  similarity float
)
LANGUAGE plpgsql
AS $function$
BEGIN
  RETURN QUERY
  SELECT 
    d.id,
    d.content,
    d.metadata,
    (1 - (d.embedding <=> query_embedding)) as similarity
  FROM documents d
  WHERE 
    (1 - (d.embedding <=> query_embedding)) > match_threshold
  ORDER BY 
    d.embedding <=> query_embedding
  LIMIT match_count;
END;
$function$;

-- ============================================
-- 4. IMPROVED CACHE SEARCH
-- ============================================
CREATE OR REPLACE FUNCTION match_cache_improved(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.92
)
RETURNS TABLE (
  id uuid,
  content text,
  metadata jsonb,
  similarity float
)
LANGUAGE plpgsql
AS $function$
BEGIN
  RETURN QUERY
  SELECT 
    sc.id,
    sc.content,
    sc.metadata,
    (1 - (sc.embedding <=> query_embedding)) as similarity
  FROM semantic_cache sc
  WHERE 
    (1 - (sc.embedding <=> query_embedding)) > match_threshold
  ORDER BY 
    sc.embedding <=> query_embedding
  LIMIT 1;
END;
$function$;

-- ============================================
-- 5. GET RELATED CHUNKS (Parent Document Retrieval)
-- ============================================
CREATE OR REPLACE FUNCTION get_related_chunks(
  source_url text,
  current_chunk_index int,
  context_window int DEFAULT 1
)
RETURNS TABLE (
  id uuid,
  content text,
  metadata jsonb,
  chunk_index int
)
LANGUAGE plpgsql
AS $function$
BEGIN
  RETURN QUERY
  SELECT 
    d.id,
    d.content,
    d.metadata,
    (d.metadata->>'chunk_index')::int as chunk_index
  FROM documents d
  WHERE 
    d.metadata->>'url' = source_url
    AND (d.metadata->>'chunk_index')::int BETWEEN 
      (current_chunk_index - context_window) AND 
      (current_chunk_index + context_window)
  ORDER BY (d.metadata->>'chunk_index')::int;
END;
$function$;

-- ============================================
-- 6. STATISTICS FUNCTION (for monitoring)
-- ============================================
CREATE OR REPLACE FUNCTION get_rag_stats()
RETURNS TABLE (
  total_documents bigint,
  total_cache_entries bigint,
  unique_urls bigint,
  avg_chunks_per_doc numeric
)
LANGUAGE plpgsql
AS $function$
BEGIN
  RETURN QUERY
  SELECT 
    COUNT(*)::bigint as total_documents,
    (SELECT COUNT(*)::bigint FROM semantic_cache) as total_cache_entries,
    COUNT(DISTINCT metadata->>'url')::bigint as unique_urls,
    ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT metadata->>'url'), 0), 2) as avg_chunks_per_doc
  FROM documents;
END;
$function$;

-- ============================================
-- 7. CREATE INDEXES (if not exist)
-- ============================================

CREATE INDEX IF NOT EXISTS idx_documents_content_fts 
ON documents USING gin(to_tsvector('english', content));

CREATE INDEX IF NOT EXISTS idx_documents_metadata_url 
ON documents USING btree((metadata->>'url'));

CREATE INDEX IF NOT EXISTS idx_documents_metadata_title 
ON documents USING btree((metadata->>'title'));

CREATE INDEX IF NOT EXISTS idx_cache_created_at 
ON semantic_cache(created_at DESC);

-- ============================================
-- 8. GRANTS (ensure n8n can execute)
-- ============================================
GRANT EXECUTE ON FUNCTION match_documents_hybrid TO anon, authenticated;
GRANT EXECUTE ON FUNCTION match_documents_simple TO anon, authenticated;
GRANT EXECUTE ON FUNCTION match_cache_improved TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_related_chunks TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_rag_stats TO anon, authenticated;

-- ============================================
-- 9. TEST THE FUNCTIONS
-- ============================================

SELECT * FROM get_rag_stats();