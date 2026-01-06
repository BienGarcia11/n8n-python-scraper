# Deployment Guide for Railway

This guide provides step-by-step instructions for deploying the RAG Scraper Worker to Railway.

## Prerequisites

Before deploying, ensure you have:
- Railway account (free tier available)
- Supabase project with pgvector enabled
- OpenAI API key with sufficient quota
- GitHub account (for deployment)

## Step 1: Supabase Setup

### 1.1 Create Supabase Project

1. Go to [supabase.com](https://supabase.com)
2. Create a new project
3. Wait for initialization (~2 minutes)

### 1.2 Enable pgvector Extension

1. Go to **SQL Editor** in Supabase dashboard
2. Run the following command:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Verify extension is enabled:
   ```sql
   SELECT * FROM pg_extension WHERE extname = 'vector';
   ```

### 1.3 Run Database Migrations

1. In **SQL Editor**, run `migrations/001_initial_schema.sql`
2. (Optional) Run `migrations/002_sample_data.sql` for test data
3. Verify tables created:
   ```sql
   SELECT table_name FROM information_schema.tables 
   WHERE table_schema = 'public';
   ```

### 1.4 Get Credentials

1. Go to **Project Settings** → **API**
2. Copy:
   - **Project URL** → Use for `SUPABASE_URL`
   - **service_role key** → Use for `SUPABASE_KEY` (NOT anon key!)

**Important**: Use `service_role` key, not `anon` key. Service role bypasses RLS policies needed for the worker.

## Step 2: Railway Setup

### 2.1 Create Railway Project

Option A: Via Dashboard
1. Go to [railway.app](https://railway.app)
2. Click **New Project**
3. Click **Deploy from GitHub repo**

Option B: Via CLI
```bash
npm install -g @railway/cli
railway login
railway init
```

### 2.2 Set Environment Variables

In Railway dashboard, go to **Variables** tab and add:

**Required Variables:**

| Variable | Description | Example |
|----------|-------------|----------|
| `SUPABASE_URL` | Supabase project URL | `https://xxx.supabase.co` |
| `SUPABASE_KEY` | Service role key | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-proj-xxx...` |

**Optional Variables (Recommended):**

| Variable | Default | Description |
|----------|----------|-------------|
| `PYTHONUNBUFFERED` | `1` | Force stdout flush for logs |
| `PLAYWRIGHT_BROWSERS_PATH` | `/ms-playwright` | Browser installation path |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `MAX_CONCURRENT_URLS` | `3` | Parallel URL processing limit |
| `RETRY_ATTEMPTS` | `3` | Maximum retry attempts |
| `POLL_INTERVAL` | `5` | Seconds between queue polls |

**Configuration Notes:**

- `MAX_CONCURRENT_URLS=3`: Start with 3, adjust based on:
  - Railway service tier memory limits
  - OpenAI rate limits (100K TPM for standard tier)
  - Expected content size per URL

- `RETRY_ATTEMPTS=3`: Balance between:
  - Processing reliability
  - Time spent on failed URLs
  - API quota consumption

- `POLL_INTERVAL=5`: Frequency of queue checks:
  - Lower = faster processing (more frequent polls)
  - Higher = less resource usage
  - Default 5 seconds is a good balance

### 2.3 Deploy to Railway

Option A: From GitHub
1. Push code to GitHub repository
2. In Railway, click **New Project** → **Deploy from GitHub repo**
3. Select your repository
4. Railway will auto-detect Dockerfile
5. Click **Deploy**

Option B: From CLI
```bash
# Deploy from current directory
railway up

# Or deploy from GitHub
railway link
railway up
```

### 2.4 Verify Deployment

1. Go to Railway dashboard → **Services** → **rag-scraper**
2. Check **Logs** tab for startup messages:
   ```
   Initializing RAG Scraper Worker...
   Initializing async components...
   Supabase client initialized
   Starting Playwright...
   Playwright browser started successfully
   Starting RAG Scraper Worker...
   Polling for pending URLs...
   ```

3. Check **Metrics** for:
   - CPU usage (should be low when idle)
   - Memory usage (expected: 500MB-1GB)
   - Network traffic (should see outbound traffic)

## Step 3: Testing

### 3.1 Add Test URLs

In Supabase SQL Editor:
```sql
INSERT INTO url_queue (url) VALUES
  ('https://example.com'),
  ('https://docs.python.org/3/tutorial/index.html'),
  ('https://www.supabase.com/docs/guides/auth');
```

### 3.2 Monitor Processing

Watch Railway logs for:
```
Processing URL 1: https://example.com
Scraping https://example.com
Extracting content from https://example.com
Chunking content from https://example.com
Generating embeddings for 5 chunks
Stored 5 documents in Supabase
Successfully processed URL 1: https://example.com
```

### 3.3 Verify Results

Check documents in Supabase:
```sql
SELECT 
  id,
  url,
  title,
  chunk_index,
  total_chunks,
  created_at
FROM documents
ORDER BY created_at DESC
LIMIT 10;
```

Check queue status:
```sql
SELECT 
  status,
  COUNT(*) as count
FROM url_queue
GROUP BY status;
```

Expected output:
```
status    | count
-----------+-------
completed  | 3
```

## Step 4: Scaling

### 4.1 Horizontal Scaling

For higher throughput, run multiple instances:

1. In Railway, go to **Settings** → **Scale**
2. Increase **Instances** (e.g., from 1 to 3)
3. Each instance will process URLs independently

**Considerations:**
- More instances = higher cost
- May hit Supabase/OpenAI rate limits faster
- Each instance consumes memory

### 4.2 Vertical Scaling

For larger pages or more concurrency:

1. Upgrade Railway service tier
2. Increase `MAX_CONCURRENT_URLS` environment variable
3. Monitor memory usage

**Recommended tiers:**
- **Free Tier**: 1-2 concurrent URLs, ~10-15 URLs/hour
- **Basic ($5/mo)**: 3-5 concurrent URLs, ~30-50 URLs/hour
- **Standard ($20/mo)**: 5-10 concurrent URLs, ~80-150 URLs/hour

### 4.3 Database Scaling

If document count grows large:

```sql
-- Check table size
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

For >1M documents, consider:
- Increasing PostgreSQL instance size
- Adding indexes for common query patterns
- Implementing partitioning by date

## Step 5: Monitoring

### 5.1 Railway Monitoring

Enable these in Railway dashboard:

1. **Metrics** (automatic):
   - CPU usage
   - Memory usage
   - Network traffic
   - Response times

2. **Logs**:
   - Real-time log streaming
   - Search and filter logs
   - Download logs for analysis

3. **Alerts** (Pro tier):
   - Service crashes
   - High memory usage
   - Deployment failures

### 5.2 Supabase Monitoring

1. **Dashboard**:
   - Database size
   - Request count
   - Query performance

2. **Logs**:
   - Query errors
   - Slow queries
   - Connection issues

3. **Database Insights** (Pro tier):
   - Query optimization
   - Index usage
   - Table analysis

### 5.3 OpenAI Monitoring

1. Go to [platform.openai.com](https://platform.openai.com)
2. Check **Usage**:
   - Token consumption
   - API call count
   - Rate limit status

3. Set up **Budget alerts** to avoid surprise costs

### 5.4 Custom Monitoring (Optional)

Add logging to external services:

```python
# In main.py, add:
import logging
from logging.handlers import RotatingFileHandler

# File logging
file_handler = RotatingFileHandler(
    'worker.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Or use external services like:
# - LogDNA
# - Papertrail
# - CloudWatch
# - DataDog
```

## Step 6: Troubleshooting

### Common Deployment Issues

**Issue: Container fails to start**

1. Check logs for specific error
2. Verify all environment variables are set
3. Ensure Playwright browsers installed (check Dockerfile)
4. Check Python version compatibility (3.11+)

**Issue: Supabase connection errors**

1. Verify `SUPABASE_URL` and `SUPABASE_KEY`
2. Check pgvector extension is enabled
3. Verify database tables exist
4. Check network connectivity (Railway → Supabase)

**Issue: OpenAI rate limits**

1. Check OpenAI usage dashboard
2. Reduce `MAX_CONCURRENT_URLS`
3. Increase `POLL_INTERVAL` to spread requests
4. Consider upgrading OpenAI tier

**Issue: High memory usage**

1. Check content size per URL
2. Reduce `MAX_CONCURRENT_URLS`
3. Upgrade Railway service tier
4. Monitor for memory leaks (should stay stable)

**Issue: Worker stops processing**

1. Check logs for errors
2. Verify URLs in queue: `SELECT * FROM url_queue WHERE status='pending'`
3. Restart service in Railway
4. Check signal handling (SIGTERM/SIGINT)

### Debugging Commands

```bash
# Connect to Railway service (if needed)
railway open

# View logs in real-time
railway logs

# Restart service
railway restart

# SSH into container (if supported)
railway shell

# Check environment variables
railway variables list
```

## Step 7: Cost Optimization

### 7.1 Railway Costs

- **Free Tier**: $0/mo (512MB RAM, 0.5GB disk)
- **Basic**: $5/mo (1GB RAM, 1GB disk)
- **Standard**: $20/mo (2GB RAM, 10GB disk)

**Optimization Tips:**
- Scale instances based on actual load
- Use free tier for development
- Monitor metrics and downgrade if unused

### 7.2 Supabase Costs

- **Free Tier**: 500MB DB, 1GB bandwidth
- **Pro Tier**: $25/mo (8GB DB, 50GB bandwidth)

**Optimization Tips:**
- Clean old documents regularly
- Use compression for large text
- Monitor table sizes
- Implement retention policies

### 7.3 OpenAI Costs

- **text-embedding-3-small**: $0.00002/1K tokens
- Example: 1M documents × 500 tokens = 500M tokens = ~$10

**Optimization Tips:**
- Chunk size: 500 tokens is optimal balance
- Batch embeddings: 100 chunks per API call
- Cache embeddings for duplicate content
- Filter low-quality content before embedding

### 7.4 Total Cost Estimate

For **1,000 URLs/day** (average 5 chunks each):

| Component | Usage | Monthly Cost |
|-----------|--------|--------------|
| Railway (Basic) | 1 instance | $5 |
| Supabase (Free) | 150K docs | $0 |
| OpenAI | 75M tokens | ~$1.50 |
| **Total** | | **~$6.50/month** |

## Step 8: Security Checklist

- [ ] Using `service_role` key (not `anon`)
- [ ] Environment variables set in Railway (not hardcoded)
- [ ] Non-root user in Dockerfile
- [ ] No sensitive data in logs
- [ ] HTTPS enabled for all external calls
- [ ] Rate limiting configured
- [ ] Input validation for URLs
- [ ] Regular dependency updates
- [ ] Access logging enabled
- [ ] Secrets rotated regularly

## Step 9: Backup and Recovery

### 9.1 Database Backups

Supabase automatic backups:
- **Free Tier**: Point-in-time recovery (7 days)
- **Pro Tier**: Daily backups (up to 30 days)

### 9.2 Code Backups

1. Code is in Git repository
2. Railway retains deployment history
3. Tag releases for rollback capability

### 9.3 Recovery Procedure

If worker fails:

1. **Check logs**: Identify root cause
2. **Rollback**: Deploy previous version
3. **Restore database**: Use Supabase point-in-time recovery
4. **Restart service**: Railway dashboard → **Restart**
5. **Verify**: Process test URL

## Step 10: Maintenance

### Weekly Tasks

- Review logs for errors
- Check processing statistics
- Monitor cost and usage
- Review queue backlog

### Monthly Tasks

- Update dependencies (`pip install -U -r requirements.txt`)
- Review and rotate API keys
- Clean up old documents if needed
- Optimize database tables

### Quarterly Tasks

- Review architecture for improvements
- Evaluate scaling needs
- Update documentation
- Security audit

## Support

For deployment issues:
1. Check Railway logs
2. Review Supabase dashboard
3. Verify OpenAI quota
4. Check this deployment guide
5. Consult README.md for architecture details

## Next Steps

After successful deployment:

1. **Add URLs**: Populate queue with URLs to scrape
2. **Query Documents**: Use vector similarity search in your application
3. **Monitor Performance**: Adjust configuration based on metrics
4. **Scale**: Increase instances/concurrency as needed
5. **Optimize**: Fine-tune chunking and embedding parameters

---

**Deployment Complete!** Your RAG scraper worker is now running on Railway and processing URLs for your RAG application.
