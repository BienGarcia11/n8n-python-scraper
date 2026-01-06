# RAG Scraper Worker

A robust, production-ready asynchronous Python scraper worker that ingests web content for RAG (Retrieval-Augmented Generation) applications.

## Features

- **Async Processing**: Full async/await architecture for efficient concurrent operations
- **Playwright Scraping**: Dynamic content rendering with anti-bot detection
- **Smart Content Extraction**: Trafilatura-based extraction removes navbars, ads, and clutter
- **Token-Aware Chunking**: Recursive text splitting with 500-token chunks and 50-token overlap
- **OpenAI Embeddings**: Vector generation using `text-embedding-3-small` (1536 dimensions)
- **Supabase Integration**: Async client with pgvector support for similarity search
- **Containerized**: Docker-optimized for Railway deployment
- **Production-Ready**: Comprehensive error handling, retry logic, and logging

## Architecture

```
┌─────────────┐
│  URL Queue   │ (Supabase: url_queue table)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Scraper    │ (Playwright with anti-bot detection)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Extractor   │ (Trafilatura content extraction)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Chunker    │ (Token-aware: 500 tokens, 50 overlap)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Embedder   │ (OpenAI: text-embedding-3-small)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Documents   │ (Supabase: documents table with pgvector)
└─────────────┘
```

## Project Structure

```
rag-scraper/
├── main.py                 # Main worker orchestration
├── config.py               # Configuration and environment variables
├── modules/
│   ├── __init__.py
│   ├── scraper.py          # Playwright browser management
│   ├── extractor.py        # Trafilatura content extraction
│   ├── chunker.py          # Recursive token-based chunking
│   └── embedder.py         # OpenAI embedding generation
├── migrations/
│   ├── 001_initial_schema.sql    # Database schema
│   └── 002_sample_data.sql       # Sample URLs for testing
├── requirements.txt         # Python dependencies
├── Dockerfile              # Railway container config
├── .env.example            # Environment variable template
└── README.md               # This file
```

## Setup

### Prerequisites

- Python 3.11+
- Supabase project with pgvector enabled
- OpenAI API key
- Docker (for deployment)

### Local Development

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd rag-scraper
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

4. **Set up Supabase database**:
   ```bash
   # Execute migrations in Supabase SQL Editor
   # Run: migrations/001_initial_schema.sql
   # Run: migrations/002_sample_data.sql (optional)
   ```

5. **Run the worker**:
   ```bash
   python main.py
   ```

## Database Schema

### url_queue Table

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| url | TEXT | URL to scrape (unique) |
| status | TEXT | pending, processing, completed, failed |
| error_message | TEXT | Error details if failed |
| attempts | INTEGER | Number of processing attempts |
| created_at | TIMESTAMP | When URL was added |
| updated_at | TIMESTAMP | Last status update |
| processed_at | TIMESTAMP | When successfully processed |

### documents Table

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| url | TEXT | Source URL |
| title | TEXT | Page title |
| content | TEXT | Text chunk content |
| chunk_index | INTEGER | Chunk index (0-based) |
| total_chunks | INTEGER | Total chunks for this URL |
| embedding | vector(1536) | OpenAI embedding |
| created_at | TIMESTAMP | When document was created |

## Deployment on Railway

### 1. Create Railway Project

```bash
# Using Railway CLI (optional)
railway init
```

Or create a project via Railway dashboard.

### 2. Set Environment Variables

In Railway dashboard, set these variables:

**Required:**
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Supabase service role key (not anon key)
- `OPENAI_API_KEY`: OpenAI API key for embeddings

**Optional:**
- `PYTHONUNBUFFERED=1`: Force stdout flush for logs
- `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`: Browser install path
- `LOG_LEVEL=INFO`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `MAX_CONCURRENT_URLS=3`: Parallel URL processing limit
- `RETRY_ATTEMPTS=3`: Maximum retry attempts
- `POLL_INTERVAL=5`: Seconds between queue polls

### 3. Deploy

```bash
# Deploy from GitHub
# 1. Push code to GitHub
# 2. Connect Railway to GitHub repository
# 3. Deploy

# Or using Railway CLI
railway up
```

### 4. Monitor

View logs in Railway dashboard to monitor:
- URL processing status
- Embedding generation
- Error messages
- Statistics

## Configuration

### Chunking Strategy

- **Chunk Size**: 500 tokens per chunk
- **Overlap**: 50 tokens between chunks
- **Method**: Recursive character splitting with token counting
- **Tokenizer**: OpenAI `tiktoken` for accurate tokenization

### Concurrency

- **Parallel URLs**: 3 URLs processed concurrently (configurable)
- **Browser Contexts**: Reuse single browser, new context per URL
- **Semaphore**: Controls concurrency to prevent resource exhaustion

### Anti-Bot Detection

- **User-Agent Rotation**: Random realistic user agents
- **Timing**: Random delays between actions (1-3 seconds)
- **Headers**: Standard browser headers
- **Viewport**: Common screen resolutions (1920x1080)

### Error Handling

- **Retry Logic**: 3 attempts with exponential backoff (2s, 5s, 10s)
- **Status Updates**: Immediate status changes in database
- **Graceful Shutdown**: Proper cleanup on SIGINT/SIGTERM

## Usage

### Adding URLs to Queue

```sql
-- Single URL
INSERT INTO url_queue (url) VALUES ('https://example.com/article');

-- Multiple URLs
INSERT INTO url_queue (url) VALUES
  ('https://example.com/article1'),
  ('https://example.com/article2'),
  ('https://example.com/article3');
```

### Querying Documents

```sql
-- Get all chunks for a URL
SELECT id, chunk_index, content, created_at
FROM documents
WHERE url = 'https://example.com/article'
ORDER BY chunk_index;

-- Similarity search (find similar chunks)
SELECT url, title, content, 
       embedding <=> '[<your_embedding_vector>]' AS distance
FROM documents
ORDER BY distance
LIMIT 10;
```

### Monitoring Progress

```sql
-- Queue statistics
SELECT 
  status,
  COUNT(*) as count
FROM url_queue
GROUP BY status;

-- Recent documents
SELECT url, chunk_index, total_chunks, created_at
FROM documents
ORDER BY created_at DESC
LIMIT 20;
```

## Troubleshooting

### Common Issues

**1. Browser fails to start**
- Ensure Playwright browsers are installed: `playwright install chromium`
- Check system dependencies in Dockerfile

**2. Supabase connection errors**
- Verify `SUPABASE_URL` and `SUPABASE_KEY` are correct
- Ensure pgvector extension is enabled: `CREATE EXTENSION vector;`

**3. OpenAI rate limits**
- Reduce `MAX_CONCURRENT_URLS` to limit concurrent API calls
- Check your OpenAI rate limits and quotas

**4. Memory leaks**
- Worker already handles context/page cleanup
- Monitor Railway metrics for memory usage
- Restart worker if memory grows indefinitely

**5. Empty content extraction**
- Some sites may have JavaScript-rendered content
- Try increasing `PLAYWRIGHT_TIMEOUT`
- Check if Trafilatura fallback is working

### Debugging

Enable DEBUG logging:
```bash
export LOG_LEVEL=DEBUG
python main.py
```

Check Railway logs for detailed error messages.

## Performance

- **Throughput**: ~3 URLs per minute (with average 5 chunks per URL)
- **Memory Usage**: ~500MB-1GB (depends on content size)
- **API Calls**: 1 OpenAI embedding call per 100 chunks (batched)
- **Database**: Optimized with IVFFlat index for fast similarity search

## Security

- Uses service role key for Supabase (not anon key)
- Non-root user in Docker container
- No sensitive data in logs
- Environment variables for all secrets

## License

MIT License - feel free to use and modify for your projects.

## Contributing

Contributions welcome! Please feel free to submit issues or pull requests.

## Support

For issues or questions:
- Check Railway logs for errors
- Review Supabase query performance
- Verify OpenAI API usage and limits
- Check Playwright documentation for scraping issues
