# RAG System Web Scraper

A robust, async web scraper that fetches URLs from a Supabase queue, scrapes content using Playwright, generates OpenAI embeddings, and stores the results in a Supabase documents table for RAG systems.

## Features

- **Playwright-based scraping**: Fast, reliable web scraping with JavaScript rendering
- **OpenAI embeddings**: Automatically generates embeddings for scraped content
- **Async processing**: Concurrent URL processing for efficiency
- **Error handling**: Automatic retries with exponential backoff
- **Batch processing**: Processes URLs in configurable batches
- **Status tracking**: Tracks each URL's status (pending, processing, completed, failed)
- **Docker-ready**: Containerized for easy deployment on Railway
- **Logging**: Comprehensive logging for monitoring and debugging

## Architecture

1. **URL Queue**: Reads URLs from Supabase `url_queue` table where `status = 'pending'`
2. **Scraping**: Uses Playwright to scrape web pages and extract content
3. **Content Processing**: Cleans HTML, extracts metadata, and prepares text
4. **Embedding Generation**: Sends content to OpenAI for embedding generation
5. **Document Storage**: Inserts scraped content and embeddings into Supabase `documents` table
6. **Status Updates**: Updates URL status throughout the process

## Prerequisites

- Python 3.11+
- Supabase project with `url_queue` and `documents` tables
- OpenAI API key
- Railway account (for deployment) or local environment

## Database Schema

### url_queue table
```sql
- id (bigint, primary key)
- url (text, unique)
- status (text, default: 'pending')
- created_at (timestamptz)
- updated_at (timestamptz)
- error_message (text, optional)
```

### documents table
```sql
- id (bigint, primary key)
- content (text)
- metadata (jsonb)
- embedding (vector)
- created_at (timestamptz)
- updated_at (timestamptz)
```

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/BienGarcia11/n8n-python-scraper.git
cd n8n-python-scraper
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure environment variables
Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```env
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key
EMBEDDING_MODEL=text-embedding-3-small

# Scraper Configuration
BATCH_SIZE=10
MAX_RETRIES=3
SCRAPER_TIMEOUT=30000
```

**Important**: Use the **service_role** key from Supabase, not the anon key, as the scraper needs write access.

### 4. Run locally
```bash
python scraper.py
```

## Railway Deployment

### 1. Create Railway account and install CLI
```bash
npm install -g @railway/cli
railway login
```

### 2. Initialize Railway project
```bash
railway init
```

### 3. Set environment variables
```bash
railway variables set SUPABASE_URL=https://your-project.supabase.co
railway variables set SUPABASE_KEY=your_service_role_key
railway variables set OPENAI_API_KEY=your_openai_api_key
railway variables set EMBEDDING_MODEL=text-embedding-3-small
railway variables set BATCH_SIZE=10
railway variables set MAX_RETRIES=3
railway variables set SCRAPER_TIMEOUT=30000
```

### 4. Deploy
```bash
railway up
```

### 5. Monitor deployment
```bash
railway logs
```

## Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase project URL | Required |
| `SUPABASE_KEY` | Supabase service role key | Required |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `EMBEDDING_MODEL` | OpenAI embedding model | `text-embedding-3-small` |
| `BATCH_SIZE` | URLs processed per batch | `10` |
| `MAX_RETRIES` | Max retry attempts per URL | `3` |
| `SCRAPER_TIMEOUT` | Page load timeout (ms) | `30000` |

## Usage

### Adding URLs to the queue
```sql
INSERT INTO url_queue (url, status) VALUES 
('https://example.com/article1', 'pending'),
('https://example.com/article2', 'pending');
```

### Running the scraper
The scraper will:
1. Fetch URLs with status `pending`
2. Mark them as `processing`
3. Scrape each URL with Playwright
4. Generate OpenAI embeddings
5. Insert into `documents` table
6. Mark URLs as `completed` or `failed`

### Monitoring progress
Check the `url_queue` table:
```sql
SELECT status, COUNT(*) FROM url_queue GROUP BY status;
```

### Viewing scraped documents
```sql
SELECT id, metadata->>'title' as title, metadata->>'url' as url, created_at 
FROM documents 
ORDER BY created_at DESC 
LIMIT 10;
```

## Performance Optimization

### For high-volume scraping (1000+ URLs):
- Increase `BATCH_SIZE` to 20-50
- Consider running multiple scraper instances
- Use Railway's automatic scaling
- Monitor OpenAI API rate limits

### For memory-constrained environments:
- Reduce `BATCH_SIZE` to 5
- Reduce `SCRAPER_TIMEOUT`
- Use lighter Playwright configuration

## Troubleshooting

### Scraper stops processing
- Check logs: `railway logs`
- Verify database connection
- Check OpenAI API quota
- Review failed URLs in `url_queue` table

### Timeout errors
- Increase `SCRAPER_TIMEOUT`
- Check URL accessibility
- Verify network connectivity

### Memory issues
- Reduce `BATCH_SIZE`
- Use Railway's larger plans
- Consider rate limiting

## Error Handling

The scraper implements:
- **Automatic retries**: Up to 3 attempts per URL with exponential backoff
- **Status tracking**: Each URL's status is updated throughout the process
- **Error logging**: All errors are logged with context
- **Graceful shutdown**: Proper cleanup on termination

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- Open an issue on GitHub
- Check Railway logs for runtime errors
- Review Supabase logs for database issues
