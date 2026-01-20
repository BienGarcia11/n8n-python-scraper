create table public.documents (
  id uuid primary key default gen_random_uuid(),

  content text not null,

  embedding vector(1536) not null,

  metadata jsonb default '{}'::jsonb,

  created_at timestamptz default now()
);
