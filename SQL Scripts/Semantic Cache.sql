create table public.semantic_cache (
  id uuid primary key default gen_random_uuid(),

  content text not null,

  embedding vector(1536) not null,

  metadata jsonb not null,

  created_at timestamptz default now()
);
