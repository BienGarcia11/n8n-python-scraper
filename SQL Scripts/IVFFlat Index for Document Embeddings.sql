create index on public.documents
using ivfflat (embedding vector_cosine_ops)
with (lists = 100);