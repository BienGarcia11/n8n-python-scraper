# Railway Deployment Guide - Web Scraper API

## Overview
This guide explains how to deploy the web scraper API to Railway for always-warm execution (no cold starts).

## Architecture Changes

### Before (GitHub Actions)
- n8n → GitHub Actions → Trigger scraper → Callback to n8n
- ❌ Cold starts on every execution
- ❌ Browser restarts each time
- ❌ Slower response times

### After (Railway API)
- n8n → Railway API (always warm) → Callback to n8n
- ✅ Browser stays warm between requests
- ✅ Faster response times
- ✅ HTTP-based scraping requests

## Deployment Steps

### 1. Create Railway Project

1. Go to [railway.app](https://railway.app)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose: `BienGarcia11/n8n-python-scraper`

### 2. Configure Railway Settings

Railway will automatically detect the Dockerfile and configure:
- **Port**: 8000 (from railway.toml)
- **Health Check**: `/health` endpoint
- **Auto-restart**: Enabled

### 3. Environment Variables (Optional)

Set these in Railway dashboard if needed:
- `PORT`: 8000 (auto-configured by railway.toml)

### 4. Get Railway URL

After deployment, Railway will provide:
- **Public URL**: `https://your-project-name.up.railway.app`
- Copy this URL for n8n configuration

## API Endpoints

### POST /scrape
Scrape multiple URLs

**Request:**
```json
{
  "urls": [
    "https://example.com/page1",
    "https://example.com/page2"
  ],
  "callback_url": "https://n8n-instance.com/webhook/callback"
}
```

**Response:**
```json
{
  "results": [
    {
      "url": "https://example.com/page1",
      "title": "Page Title",
      "content": "Extracted content...",
      "status": "success"
    }
  ],
  "total_urls": 2,
  "successful": 2,
  "failed": 0
}
```

### GET /health
Health check endpoint

**Response:**
```json
{
  "status": "healthy",
  "browser_warm": true
}
```

## Benefits of Railway Deployment

### Always Warm Browser
- Browser initializes on startup (not per-request)
- Context stays warm between requests
- Faster first response

### HTTP API
- Simple REST API
- Can be called from any service
- No GitHub Actions dependency

### Scalable
- Railway automatically scales based on traffic
- Built-in health checks
- Auto-restart on failure

### Monitoring
- Railway provides logs
- Metrics dashboard
- Error tracking

## Testing Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run API server
uvicorn api_server:app --reload

# Test endpoint
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com"],
    "callback_url": "https://your-n8n.com/callback"
  }'
```

## Updating n8n Workflow

Replace the "Trigger GitHub Scraper" node:

**Old Node (HTTP Request to GitHub Actions):**
- Method: POST
- URL: `https://api.github.com/repos/.../actions/workflows/scrape.yml/dispatches`
- Body: Complex GitHub Actions format

**New Node (HTTP Request to Railway API):**
- Method: POST
- URL: `https://your-railway-app.up.railway.app/scrape`
- Body:
```json
{
  "urls": "={{ $json.batch_urls }}",
  "callback_url": "={{ $execution.resumeUrl }}"
}
```

## Cost Considerations

Railway Pricing (as of 2025):
- **Free Tier**: $5/month credit
- **Hobby**: $5/month (512MB RAM, 0.5 vCPU)
- **Pro**: $20/month (2GB RAM, 1 vCPU)

This scraper uses:
- ~512MB RAM (Playwright + Chrome)
- 1 vCPU (for parallel scraping)

**Recommendation**: Hobby tier should handle 5 concurrent requests well.

## Monitoring

### Railway Dashboard
- View logs in real-time
- Monitor response times
- Track errors

### Health Checks
- Automatic health checks every 30s
- Auto-restart on failure
- Status available at `/health`

## Troubleshooting

### Browser Cold Start on First Request
- **Cause**: First request after deployment
- **Solution**: Wait ~40s for startup to complete

### Timeout Errors
- **Cause**: URLs taking too long to load
- **Solution**: Increase timeout in api_server.py (line: `timeout=30000`)

### Memory Issues
- **Cause**: Too many concurrent requests
- **Solution**: Reduce semaphore count (line: `semaphore = asyncio.Semaphore(5)`)

### Railway URL Not Working
- **Cause**: Domain not propagated
- **Solution**: Wait 5-10 minutes after deployment

## Next Steps

1. ✅ Deploy to Railway
2. ✅ Test `/health` endpoint
3. ✅ Test `/scrape` endpoint with sample URLs
4. ✅ Update n8n workflow to use Railway URL
5. ✅ Remove GitHub Actions integration
6. ✅ Monitor Railway logs
