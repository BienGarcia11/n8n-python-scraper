-- Insert sample URLs to the queue
-- These are example documentation and news sites

INSERT INTO url_queue (url) VALUES
  ('https://docs.python.org/3/tutorial/index.html'),
  ('https://www.supabase.com/docs/guides/auth'),
  ('https://openai.com/blog/chatgpt'),
  ('https://www.theverge.com/tech'),
  ('https://github.com/features/copilot')
ON CONFLICT (url) DO NOTHING;

-- Verify insertion
SELECT id, url, status, created_at FROM url_queue ORDER BY id DESC LIMIT 10;
