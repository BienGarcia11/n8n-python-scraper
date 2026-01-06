# Web Scraper with RAG Integration

A robust, high-performance web scraper that processes URLs from a Supabase queue, scrapes content using Playwright, generates embeddings with OpenAI, and stores the data in Supabase for RAG (Retrieval-Augmented Generation) systems.

## Features

- **Concurrent Scraping**: Processes multiple URLs simultaneously (configurable)
- **Playwright-based Scraping**: Handles dynamic JavaScript content
- **OpenAI Embeddings**: Generates embeddings using text-embedding-3-small model
- **Supabase Integration**: Seamless integration with `url_queue` and `documents` tables
- **Error Handling**: Automatic retry with exponential backoff
- **Status Tracking**: Tracks URL processing status (pending, processing, completed, failed)
- **Containerized**: Ready for Railway deployment
- **Production Ready**: Includes logging, monitoring, and error recovery

## Architecture

```
url_queue (Supabase) → Web Scraper → OpenAI Embeddings → documents (Supabase)
```

### Database Schema

**url_queue table:**
- `id`: Unique identifier
- `url`: URL to scrape
- `status`: pending | processing | completed | failed
- `created_at`: Timestamp
- `updated_at`: Timestamp

**documents table:**
- `id`: Unique identifier
- `content`: Scraped text content
- `metadata`: JSON containing URL, title, scrape date
- `embedding`: Vector embedding (1536 dimensions)
- `created_at`: Timestamp
- `updated_at`: Timestamp

## Setup

### Prerequisites

- Python 3.11+
- Supabase project with `url_queue` and `documents` tables
- OpenAI API key

### Local Setup

1. **Clone the repository:**
```bash
git clone https://github.com/BienGarcia11/n8n-python-scraper.git
cd n8n-python-scraper
```

2. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Install Playwright browsers:**
```bash
playwright install chromium
playwright install-deps chromium
```

5. **Configure environment variables:**
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```env
SUPABASE_URL=https://ykohyrwipxpwztptfopi.supabase.co
SUPABASE_SERVICE_KEY=your-service-key-here
OPENAI_API_KEY=your-openai-api-key-here
MAX_URLS_PER_RUN=100
```

6. **Run the scraper:**
```bash
python scraper.py
```

## Railway Deployment

The scraper is configured for Railway deployment with automatic builds.

### Setup Steps

1. **Link Railway project:**
```bash
railway link
```

2. **Set environment variables in Railway:**
```bash
railway variables set SUPABASE_URL=https://ykohyrwipxpwztptfopi.supabase.co
railway variables set SUPABASE_SERVICE_KEY=your-service-key
railway variables set OPENAI_API_KEY=your-openai-api-key
railway variables set MAX_URLS_PER_RUN=100
```

3. **Deploy:**
```bash
railway up
```

Railway will automatically:
- Build the Docker image
- Install Playwright and dependencies
- Deploy the scraper
- Set up health checks
- Monitor and restart on failure

### Monitoring

View logs in Railway:
```bash
railway logs
```

## Configuration

### Environment Variables

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `SUPABASE_URL` | Yes | Supabase project URL | - |
| `SUPABASE_SERVICE_KEY` | Yes | Supabase service key (not anon key) | - |
| `OPENAI_API_KEY` | Yes | OpenAI API key | - |
| `MAX_URLS_PER_RUN` | No | Maximum URLs to process per run | 100 |

### Scraper Settings

Edit `scraper.py` to adjust:

- `max_concurrent_scrapes`: Number of concurrent URL processing (default: 5)
- `page_timeout`: Page load timeout in ms (default: 30000)
- `embedding_model`: OpenAI embedding model (default: text-embedding-3-small)
- `max_content_length`: Max content length for embeddings (default: 8191)

## Usage

### Adding URLs to Queue

Insert URLs into the `url_queue` table with status `'pending'`:

```sql
INSERT INTO url_queue (url, status)
VALUES 
  ('https://example.com/page1', 'pending'),
  ('https://example.com/page2', 'pending'),
  ('https://example.com/page3', 'pending');
```

### Processing Workflow

1. Scraper fetches URLs with `status = 'pending'`
2. Marks URL as `status = 'processing'`
3. Scrapes content using Playwright
4. Generates OpenAI embedding
5. Saves to `documents` table
6. Marks URL as `status = 'completed'` (or `'failed'` on error)

### Querying Documents

Use vector similarity search in Supabase:

```sql
SELECT 
  id,
  content,
  metadata->>'title' as title,
  metadata->>'url' as url,
  1 - (embedding <=> '[your_query_embedding]') as similarity
FROM documents
ORDER BY embedding <=> '[your_query_embedding]'
LIMIT 10;
```

## Error Handling

The scraper includes robust error handling:

- **Automatic retries**: Failed operations retry 3 times with exponential backoff
- **Status tracking**: Failed URLs marked with error messages
- **Logging**: Detailed logs for debugging
- **Graceful shutdown**: Properly closes browser and connections

## Performance

- **Concurrent processing**: Processes 5 URLs simultaneously (configurable)
- **Efficient scraping**: Playwright waits for network idle
- **Batch operations**: Processes up to 100 URLs per run
- **Resource management**: Proper cleanup and memory management

## Troubleshooting

### Common Issues

**Browser fails to launch:**
```bash
playwright install-deps chromium
```

**Supabase connection errors:**
- Verify `SUPABASE_SERVICE_KEY` (not `SUPABASE_ANON_KEY`)
- Check network connectivity
- Verify table permissions

**OpenAI API errors:**
- Verify `OPENAI_API_KEY` is valid
- Check API quota and billing
- Ensure embedding model access

**Memory issues:**
- Reduce `max_concurrent_scrapes`
- Reduce `MAX_URLS_PER_RUN`
- Monitor Railway memory usage

## Development

### Running Tests

```bash
pytest tests/
```

### Adding Features

The modular design makes it easy to extend:
- Add custom text processors
- Implement different scraping strategies
- Add caching layers
- Implement rate limiting
- Add proxy support

## License

MIT License - feel free to use this project for your own purposes.

## Support

For issues or questions:
1. Check the logs for error messages
2. Review this README
3. Open an issue on GitHub

## Roadmap

- [ ] Add proxy support
- [ ] Implement rate limiting per domain
- [ ] Add image extraction
- [ ] Support multiple embedding models
- [ ] Add caching layer
- [ ] Implement scheduling
- [ ] Add web UI for monitoring
- [ ] Support custom user agents
