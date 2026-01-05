# RAG System Web Scraper

A robust, production-ready web scraper designed for RAG (Retrieval-Augmented Generation) systems. This scraper efficiently processes URLs from a queue, extracts comprehensive content (including dynamic and hidden elements), generates OpenAI embeddings, and stores everything in a Supabase database.

## Features

- **Thorough Content Extraction**: Handles dynamic content, lazy loading, dropdowns, and hidden elements
- **Intelligent Interaction**: Automatically clicks expandable elements, scrolls through pages, and hovers over interactive elements
- **Retry Mechanism**: Built-in retry logic with exponential backoff for reliability
- **Batch Processing**: Efficient batch processing for large URL queues
- **OpenAI Embeddings**: Automatic embedding generation for RAG systems
- **Supabase Integration**: Native Supabase support for URL queue and document storage
- **Railway Ready**: Optimized for Railway deployment with Docker support
- **Comprehensive Logging**: Detailed logging for monitoring and debugging

## Architecture

### Components

1. **Browser Manager** (`scraper/browser.py`)
   - Manages Playwright browser instances
   - Handles context creation and cleanup
   - Optimizes resource usage

2. **Content Interaction** (`scraper/interactions.py`)
   - Clicks expandable elements
   - Performs full-page scrolling
   - Hovers over interactive elements
   - Waits for dynamic content

3. **Content Extractor** (`scraper/extractor.py`)
   - Extracts page content and metadata
   - Cleans and normalizes text
   - Validates content quality

4. **Embedding Generator** (`embeddings/generator.py`)
   - Generates OpenAI embeddings
   - Batch processing for efficiency
   - Token counting and truncation

5. **Database Manager** (`database.py`)
   - Supabase CRUD operations
   - URL queue management
   - Document storage with embeddings

## Setup

### Prerequisites

- Python 3.11+
- Supabase project with `url_queue` and `documents` tables
- OpenAI API key
- Railway account (for deployment)

### Local Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/BienGarcia11/n8n-python-scraper.git
   cd n8n-python-scraper
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers**
   ```bash
   playwright install chromium
   playwright install-deps chromium
   ```

5. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

### Environment Variables

Create a `.env` file with the following variables:

```env
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key-here

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key-here
EMBEDDING_MODEL=text-embedding-3-small

# Scraper Configuration
CONCURRENCY_LIMIT=5
BATCH_SIZE=50
MAX_RETRIES=3
TIMEOUT_SECONDS=30
SCROLL_WAIT_MS=1000
INTERACTION_WAIT_MS=1000

# Logging
LOG_LEVEL=INFO
```

**Important**: Use the **service role key** for Supabase, not the anon key, as the scraper needs write access.

## Usage

### Running Locally

```bash
python main.py
```

The scraper will:
1. Fetch pending URLs from the `url_queue` table
2. Process them in batches
3. Extract content with thorough interaction
4. Generate embeddings
5. Store results in the `documents` table
6. Update URL status (pending → processing → completed/failed)

### Monitoring Progress

The scraper logs progress to:
- Console (stdout)
- `scraper.log` file

Progress information includes:
- URLs processed
- Success/failure count
- Word/character counts
- Error messages

## Database Schema

### url_queue Table

```sql
CREATE TABLE url_queue (
    id BIGINT PRIMARY KEY DEFAULT NEXTVAL('url_queue_id_seq'),
    url TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### documents Table

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY DEFAULT NEXTVAL('documents_id_seq'),
    content TEXT NOT NULL,
    metadata JSONB NOT NULL,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Railway Deployment

### Automatic Deployment

1. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Initial commit"
   git push origin main
   ```

2. **Create Railway Project**
   - Go to [Railway](https://railway.app)
   - Click "New Project" → "Deploy from GitHub"
   - Select your repository

3. **Configure Environment Variables**
   In Railway dashboard, add all environment variables from `.env.example`

4. **Deploy**
   Railway will automatically build and deploy using the Dockerfile

### Manual Deployment with Railway CLI

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Set environment variables
railway variables set SUPABASE_URL="https://your-project.supabase.co"
railway variables set SUPABASE_SERVICE_KEY="your-service-role-key"
railway variables set OPENAI_API_KEY="your-openai-api-key"
# ... add other variables

# Deploy
railway up
```

## Performance

### Expected Performance

With 4,988 URLs in thorough mode:
- **Processing time**: 8-12 hours
- **Processing rate**: 6-12 URLs/minute
- **Memory usage**: ~1-2 GB per instance
- **Railway concurrency**: 3-5 instances recommended

### Optimization Tips

1. **Adjust concurrency** based on Railway plan:
   - Starter: 2-3 concurrent instances
   - Basic: 3-5 concurrent instances
   - Pro: 5-10 concurrent instances

2. **Tune batch size**:
   - Smaller batches (25-50): Better for error recovery
   - Larger batches (100-200): Better throughput

3. **Optimize timeout**:
   - Faster sites: 15-20 seconds
   - Complex sites: 30-40 seconds

## Troubleshooting

### Common Issues

**1. Playwright Browser Fails to Start**
```bash
# Reinstall Playwright browsers
playwright install chromium --force
playwright install-deps chromium
```

**2. Memory Errors**
- Reduce `CONCURRENCY_LIMIT`
- Reduce `BATCH_SIZE`

**3. Timeout Errors**
- Increase `TIMEOUT_SECONDS`
- Check network connectivity
- Verify URLs are accessible

**4. Database Connection Errors**
- Verify Supabase URL and key
- Check service role key permissions
- Ensure database is accessible

**5. OpenAI API Errors**
- Verify API key is valid
- Check API quota/limits
- Ensure billing is enabled

### Debug Mode

Set `LOG_LEVEL=DEBUG` for detailed logging:

```env
LOG_LEVEL=DEBUG
```

## Content Extraction Strategy

The scraper uses a **thorough mode** by default to handle complex websites:

1. **Initial Load**: Wait for network idle
2. **Expand Elements**: Click all dropdowns, accordions, "Read More" buttons
3. **Hover Interactions**: Hover over menu items and dropdowns
4. **First Scroll**: Incremental scroll to trigger lazy loading
5. **Wait for Content**: Wait for dynamic content to load
6. **Second Expand**: Check for newly appeared expandable elements
7. **Final Scroll**: Another pass to catch remaining lazy-loaded content

This ensures maximum content extraction, even from complex web applications.

## Error Handling

The scraper implements robust error handling:

- **Automatic retries**: 3 attempts with exponential backoff
- **Status tracking**: URLs marked as processing/completed/failed
- **Error logging**: Detailed error messages in database
- **Graceful degradation**: Continues processing even if some URLs fail
- **Cleanup**: Proper browser and resource cleanup on errors

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is part of the RAG System with Semantic Cache.

## Support

For issues or questions:
- Check the logs in `scraper.log`
- Review Railway deployment logs
- Verify environment variables are correctly set

## Acknowledgments

- [Playwright](https://playwright.dev/) - Browser automation
- [Supabase](https://supabase.com/) - Backend database
- [OpenAI](https://openai.com/) - Embedding generation
- [Railway](https://railway.app/) - Deployment platform
