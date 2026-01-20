create or replace function match_cache (
  query_embedding vector(1536),
  match_threshold float
)
returns table (
  id uuid,
  content text,
  metadata jsonb,
  similarity float
)
language sql stable
as $$
  select
    semantic_cache.id,
    semantic_cache.content,
    semantic_cache.metadata,
    1 - (semantic_cache.embedding <=> query_embedding) as similarity
  from semantic_cache
  where 1 - (semantic_cache.embedding <=> query_embedding) > match_threshold
  order by similarity desc
  limit 1;
$$;
