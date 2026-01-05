# Bulk Web Scraper for RAG

A high-performance web scraping service built with Playwright, designed for RAG (Retrieval-Augmented Generation) systems. Features automatic content expansion, OpenAI embeddings generation, and Supabase integration.

## Features

- **Playwright-based Scraping**: Robust content extraction with multi-step fallback strategy
- **Automatic Content Expansion**: Expands hidden content (accordions, dropdowns, tabs)
- **RAG Integration**: Automatic embedding generation using OpenAI's text-embedding-3-small
- **Concurrent Processing**: Process 2-3 URLs concurrently with semaphore control
- **Validation System**: Detects phantom completions, missing embeddings, and stuck jobs
- **Railway Ready**: Optimized Docker configuration for Railway deployment
- **n8n Integration**: HTTP webhooks for seamless workflow automation

## Architecture

### Reference Code Blocks (Preserved from Previous System)

- **A. Expand Hidden Content**: Multi-pass expansion with common selectors
- **B. Browser Launch Args**: Railway-optimized Chromium arguments
- **C. Cookie Handling**: Automatic cookie consent dialog dismissal
- **D. 4-Step Extraction**: Smart content extraction with fallbacks

### Database Schema

**url_queue** (Source Table)
- `id`: Bigint primary key
- `url`: Text (unique)
- `status`: Text ('pending', 'processing', 'completed', 'failed')
- `created_at`: Timestamp with timezone
- `updated_at`: Timestamp with timezone

**documents** (Destination Table)
- `id`: Bigint primary key
- `content`: Text (full cleaned text)
- `metadata`: JSONB (source URL, title)
- `embedding`: Vector (pgvector, 1536 dimensions)
- `created_at`: Timestamp with timezone
- `updated_at`: Timestamp with timezone

## API Endpoints

### `GET /health_check`
Returns service status and version.

**Response:**
```json
{
  "status": "healthy",
  "service": "bulk-web-scraper",
  "version": "1.0.0"
}
```

### `POST /start_bulk_scrape`
Begin the scraping job. Responds immediately, processes in background.

**Response:**
```json
{
  "message": "Bulk scrape started for 50 URLs",
  "urls_queued": 50
}
```

### `GET /scraping_status`
Check the status of the queue and current job.

**Response:**
```json
{
  "is_scraping": true,
  "pending_count": 30,
  "processing_count": 5,
  "completed_count": 15,
  "failed_count": 0
}
```

### `GET /validate`
Run validation checks on the scraped data.

**Response:**
```json
{
  "phantom_completions": ["https://example.com/page1"],
  "missing_embeddings": [1, 2, 3],
  "stuck_urls": ["https://example.com/page2"],
  "total_issues": 4
}
```

### `POST /validate-fix`
Automatically fix validation errors.

**Response:**
```json
{
  "fixed": 3,
  "failed": 1
}
```

### `POST /reset_to_pending`
Reset URLs in the queue back to 'pending' status.

**Response:**
```json
{
  "message": "Reset 10 URLs to pending status",
  "reset_count": 10
}
```

### `POST /stop_scraping_work`
Immediately terminate any active scraping processes.

**Response:**
```json
{
  "message": "Scraping process termination requested",
  "success": true
}
```

## Environment Variables

Create a `.env` file (or configure in Railway):

```env
# Required
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-service-role-key
OPENAI_API_KEY=sk-your-openai-api-key

# Optional
MAX_BULK_URLS=100  # Default: 100

# Railway (automatically set)
PORT=8000
```

## Local Development

### Prerequisites
- Python 3.12+
- Supabase project with pgvector extension
- OpenAI API key

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-name>
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your credentials
```

5. Run the server:
```bash
python api_server.py
```

The server will start on `http://localhost:8000`

## Railway Deployment

### Prerequisites
- Railway account
- Supabase project credentials
- OpenAI API key

### Setup

1. Install Railway CLI:
```bash
npm install -g @railway/cli
railway login
```

2. Link to Railway:
```bash
railway init
```

3. Set environment variables:
```bash
railway variables set SUPABASE_URL=https://your-project.supabase.co
railway variables set SUPABASE_KEY=your-supabase-service-role-key
railway variables set OPENAI_API_KEY=sk-your-openai-api-key
railway variables set MAX_BULK_URLS=100
```

4. Deploy:
```bash
railway up
```

5. Get the deployed URL:
```bash
railway domain
```

### Railway-Specific Optimizations

The Dockerfile includes:
- Railway-optimized browser launch arguments
- System dependencies for Chromium (manually installed to avoid Playwright dependency issues)
- Non-root user for security
- Health check endpoint monitoring
- Proper port configuration via `PORT` environment variable

**Note:** The Dockerfile manually installs required system dependencies instead of using `playwright install-deps` to avoid package conflicts on Railway's Metal builder.

## n8n Integration

This service is designed to work seamlessly with n8n workflows via HTTP Request nodes.

### Example n8n Workflow

1. **HTTP Request - Start Scraping**
   - Method: POST
   - URL: `{{RAILWAY_URL}}/start_bulk_scrape`
   - Response: URLs queued count

2. **Wait / Poll**
   - Wait: 10 seconds
   - Loop 20 times

3. **HTTP Request - Check Status**
   - Method: GET
   - URL: `{{RAILWAY_URL}}/scraping_status`
   - Response: Queue counts

4. **HTTP Request - Validate**
   - Method: GET
   - URL: `{{RAILWAY_URL}}/validate`
   - Response: Validation issues

5. **HTTP Request - Fix Issues** (if issues found)
   - Method: POST
   - URL: `{{RAILWAY_URL}}/validate-fix`
   - Response: Fix results

## Token Limits

The embedding model `text-embedding-3-small` has an 8,191 token limit. The scraper automatically truncates text to approximately 32,000 characters (4 chars per token estimate) to stay within limits.

## Scraping Strategy

The 4-step content extraction strategy:

1. **Main/Article**: Look for `<main>` or `<article>` elements
2. **Help Center**: Look for article/docs class selectors
3. **Body Fallback**: Remove nav/header/footer via JavaScript
4. **Last Resort**: Get all body text

Each step includes a fallback to the next if no content is found.

## Troubleshooting

### Scraping fails with "no content found"
- Check if the website blocks automated access
- Verify the URL is accessible
- Check browser launch arguments in `scraper.py`

### Embeddings generation fails
- Verify OPENAI_API_KEY is correct
- Check OpenAI API quota and rate limits
- Ensure text doesn't exceed token limits

### Railway deployment issues
- Check Railway logs: `railway logs`
- Verify all environment variables are set
- Ensure PORT variable is not manually set (Railway sets it)

### Validation issues
- Phantom completions: URLs marked 'completed' but missing from documents
- Missing embeddings: Documents with content but NULL embedding column
- Stuck URLs: URLs in 'processing' status for > 1 hour

Use `/validate-fix` endpoint to automatically resolve these issues.

## Performance

- **Concurrency**: 2-3 URLs processed simultaneously
- **Timeout**: 30 seconds per URL
- **Browser**: Chromium with Railway-optimized arguments
- **Memory**: Efficient memory usage with proper cleanup

## License

MIT

## Support

For issues and questions, please refer to the project documentation or create an issue in the repository.
