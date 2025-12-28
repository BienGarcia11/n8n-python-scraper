# Railway Configuration Guide

This guide explains how to configure the bulk scraper settings in Railway.

## Configurable Environment Variables

The bulk scraper now supports these environment variables:

### 1. `MAX_BULK_URLS`

**Description**: Maximum number of URLs to scrape per bulk run

**Default**: `100`

**Purpose**: Safety limit to prevent resource overload

**Recommended Values**:
- **100**: Conservative, takes ~10-15 minutes per run
- **500**: Moderate, takes ~30-45 minutes per run
- **1000**: Aggressive, takes ~1-2 hours per run
- **5000**: Scrapes all at once (may timeout Railway)

**Example Usage**:
```toml
MAX_BULK_URLS = "500"
```

---

### 2. `EMBEDDING_MODEL`

**Description**: OpenAI embedding model to use for vector search

**Default**: `text-embedding-3-small`

**Available Models**:

| Model | Dimensions | Cost | Quality |
|--------|------------|-------|----------|
| `text-embedding-3-small` | 1,536 | $0.00002/1K tokens | **Recommended** |
| `text-embedding-3-large` | 3,072 | $0.00013/1K tokens | Higher quality |
| `text-embedding-ada-002` | 1,536 | $0.0001/1K tokens | Legacy |

**Example Usage**:
```toml
EMBEDDING_MODEL = "text-embedding-3-large"
```

---

## How to Configure in Railway

### Method 1: Via Railway Dashboard (GUI)

1. Go to your Railway project: https://railway.com/project/7e1040e9-1c32-4451-be65-8f2135b57ae9
2. Click on **n8n-python-scraper** service
3. Go to **Variables** tab
4. Click **New Variable**
5. Add variable:
   - **Name**: `MAX_BULK_URLS` or `EMBEDDING_MODEL`
   - **Value**: Your desired value (e.g., `500`)
6. Click **Add Variable**
7. Click **Redeploy** to apply changes

### Method 2: Via `railway.toml` File

Edit `railway.toml` in your project:

```toml
[build]
builder = "DOCKERFILE"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 10000

[env]
# Bulk Scraper Configuration
MAX_BULK_URLS = "500"  # Change this value
EMBEDDING_MODEL = "text-embedding-3-small"  # Change model
```

Then commit and push changes:
```bash
git add railway.toml
git commit -m "Update configuration"
git push
```

### Method 3: Via Railway CLI

```bash
railway variables set MAX_BULK_URLS=500
railway variables set EMBEDDING_MODEL=text-embedding-3-large
```

---

## Cost Estimation

### OpenAI Embeddings (text-embedding-3-small)

- **Cost**: $0.00002 per 1,000 tokens
- **Estimated per URL**: ~$0.0001 (5,000 chars ≈ 1,875 tokens)
- **For 4,988 URLs**: ~$0.50 total

### Embeddings by Model

| Model | Cost per URL | 100 URLs | 1,000 URLs | 5,000 URLs |
|--------|--------------|-----------|-------------|-------------|
| `text-embedding-3-small` | $0.0001 | $0.01 | $0.10 | $0.50 |
| `text-embedding-3-large` | $0.00065 | $0.07 | $0.65 | $3.25 |
| `text-embedding-ada-002` | $0.00005 | $0.005 | $0.05 | $0.25 |

---

## How Many Runs to Complete Scraping

With your **4,988 pending URLs**:

| MAX_BULK_URLS | Runs Needed | Time Estimate |
|---------------|-------------|---------------|
| 100 (default) | 50 runs | ~12-18 hours |
| 500 | 10 runs | ~5-7 hours |
| 1000 | 5 runs | ~5-10 hours |
| 5000 | 1 run | ~5-10 hours |

---

## Current Configuration

**railway.toml** current settings:
```toml
MAX_BULK_URLS = "100"
EMBEDDING_MODEL = "text-embedding-3-small"
```

---

## Testing Configuration

After changing configuration:

1. **Check current settings**:
   ```bash
   curl http://n8n-python-scraper-production.up.railway.app/
   ```

2. **View configuration**:
   ```bash
   curl http://n8n-python-scraper-production.up.railway.app/ | jq '.safety_limits'
   ```

3. **Trigger test scrape**:
   ```bash
   curl -X POST http://n8n-python-scraper-production.up.railway.app/scrape/bulk
   ```

---

## Troubleshooting

### Issue: Service fails to start

**Error**: `NameError: name 'os' is not defined`

**Solution**: Ensure `import os` is at the top of `api_server.py` (this has been fixed)

### Issue: Bulk scrape times out

**Cause**: `MAX_BULK_URLS` set too high

**Solution**: Reduce `MAX_BULK_URLS` to 500 or 100

### Issue: Embeddings fail

**Cause**: Invalid model name or missing `OPENAI_API_KEY`

**Solution**:
1. Verify `OPENAI_API_KEY` is set in Railway
2. Check model name spelling (case-sensitive)
3. Check OpenAI account has credits

### Issue: No documents inserted

**Cause**: Supabase credentials incorrect

**Solution**: Verify `SUPABASE_URL` and `SUPABASE_KEY` are correct

---

## Recommended Configuration

For your **4,988 URLs**:

```toml
MAX_BULK_URLS = "500"
EMBEDDING_MODEL = "text-embedding-3-small"
```

**Why this configuration?**
- **500 URLs/run**: Completes in 10 runs (manageable)
- **text-embedding-3-small**: Best balance of quality and cost
- **Total time**: ~5-7 hours (spread over days/weeks)
- **Total cost**: ~$0.50 for all embeddings

---

## Next Steps

1. **Configure via Railway Dashboard**:
   - Go to https://railway.com/project/7e1040e9-1c32-4451-be65-8f2135b57ae9
   - Click service → Variables → New Variable
   - Add `MAX_BULK_URLS=500`
   - Redeploy

2. **Or commit changes to `railway.toml`**:
   ```bash
   # Edit railway.toml
   git add railway.toml
   git commit -m "Update MAX_BULK_URLS to 500"
   git push
   ```

3. **Import n8n workflow** and start bulk scraping:
   - Import `Bulk Scraper Control Workflow.json`
   - Execute workflow to trigger bulk scrape
   - Check Railway logs for progress

---

## Support

- **Railway Documentation**: https://docs.railway.app/
- **OpenAI Embeddings**: https://platform.openai.com/docs/guides/embeddings
- **Project Repository**: https://github.com/BienGarcia11/n8n-python-scraper
