CREATE OR REPLACE FUNCTION match_documents_with_metadata(
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
    -- Vector similarity
    (1 - (d.embedding <=> query_embedding)) > match_threshold
    OR
    -- Metadata text search
    (
      (d.metadata->>'title') ILIKE '%' || query_text || '%' OR
      (d.metadata->>'url') ILIKE '%' || query_text || '%' OR
      d.content ILIKE '%' || query_text || '%'
    )
  ORDER BY 
    (1 - (d.embedding <=> query_embedding)) DESC
  LIMIT match_count;
END;
$function$;