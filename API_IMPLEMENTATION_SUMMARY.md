# HTTP API Endpoints Implementation Summary

## Overview
Added FastAPI with 6 HTTP endpoints to control the RAG scraper worker for n8n workflows integration.

## Changes Made

### 1. New Files Created

**api.py** - FastAPI application with 6 endpoints:
- `health_check` (GET) - Service health, browser state, request counts
- `scraping_status` (GET) - Bulk task progress, percentage, counts
- `start_bulk_scrape` (POST) - Start bulk processing, returns task ID
- `stop_scraping_work` (POST) - Graceful stop after current URL
- `validate` (POST) - Validate data consistency issues
- `validate-fix` (POST) - Validate and auto-fix in background

### 2. Files Modified

**requirements.txt**
- Added: `fastapi==0.104.1`
- Added: `uvicorn==0.24.0`

**main.py**
- Integrated FastAPI app instance
- Added bulk_task tracking dict
- Registered worker with API module
- Changed to run uvicorn server instead of worker loop

**modules/scraper.py**
- Added `urls_since_restart` counter
- Added `restart_browser()` method
- Added `should_restart_browser()` check (every 30 URLs)
- Integrated restart into scrape loop

**Dockerfile**
- Added `curl` package for health checks
- Exposed port 8000
- Updated health check to call `/health_check` endpoint
- Changed CMD to run FastAPI server

## API Endpoint Details

### 1. GET /health_check
Returns service health and browser state.

**Response:**
```json
{
  "status": "healthy",
  "message": "Worker running normally",
  "browser_warm": "warm",
  "requests_processed": 150,
  "service_uptime": "2024-01-06T18:00:00",
  "timestamp": "2024-01-06T18:30:00"
}
```

### 2. GET /scraping_status
Returns bulk scrape progress.

**Response:**
```json
{
  "task_id": "task-20240106-abc123",
  "status": "running",
  "total_urls": 150,
  "processed_urls": 75,
  "failed_urls": 2,
  "percentage": 50.0
}
```

### 3. POST /start_bulk_scrape
Starts bulk scraping in background.

**Response:**
```json
{
  "task_id": "task-20240106-abc123",
  "status": "started",
  "queued_urls": 150
}
```

### 4. POST /stop_scraping_work
Stops scraping after current URL finishes.

**Response:**
```json
{
  "status": "stopping",
  "urls_processed": 78,
  "message": "Stopping after 78 URLs processed"
}
```

### 5. POST /validate
Validates data consistency without fixing.

**Response:**
```json
{
  "status": "validated",
  "validation": {
    "total_urls": 200,
    "success_rate": 95.0,
    "total_issues": 10,
    "issues": {
      "missing_documents": 5,
      "stuck_processing": 5
    }
  }
}
```

### 6. POST /validate-fix
Validates and fixes data consistency in background.

**Response:**
```json
{
  "task_id": "fix-20240106-xyz789",
  "status": "fixing",
  "issues_found": 10,
  "fixed_urls": 0
}
```

## Key Features

### Non-blocking Responses
All endpoints return immediately with:
- Task ID for tracking
- Initial status
- Count/progress information
- Background work continues asynchronously

### Graceful Stop
Stop behavior:
- Sets `stop_requested` flag
- Waits for current URL to finish (max 30 seconds)
- Returns count of processed URLs
- Prevents orphaned processing tasks

### Browser Memory Management
- Tracks URLs processed since restart
- Automatically restarts browser every 30 URLs
- Prevents memory leaks from long-running sessions
- Zero-downtime restart (current URL finishes first)

### Bulk Task Tracking
In-memory state tracking:
- Task ID generation (format: task-YYYYMMDD-8chars)
- Real-time percentage calculation
- Processed/failed URL counts
- Status lifecycle: idle → running → completed/error

### Validation Logic
Checks for two types of issues:
1. **Missing Documents** - URLs marked 'completed' but no documents exist
2. **Stuck Processing** - URLs stuck in 'processing' for >1 hour

Fixes:
- Reset missing documents to 'pending'
- Reset stuck processing to 'pending'
- Clear error messages
- Update timestamps

## Deployment

### Railway Configuration
- **Port**: 8000 (exposed)
- **Health Check**: GET /health_check every 30s
- **Environment Variables** (from Railway dashboard):
  - `OPENAI_API_KEY` - OpenAI API key
  - `SUPABASE_URL` - Supabase project URL
  - `SUPABASE_KEY` - Supabase service key
  - `PLAYWRIGHT_BROWSERS_PATH` - Path to Playwright browsers

### API Documentation
FastAPI provides automatic API documentation at:
- Swagger UI: `http://<railway-domain>/docs`
- ReDoc: `http://<railway-domain>/redoc`

## n8n Integration

### Workflow Example
1. **Start Bulk Scrape** → Call `POST /start_bulk_scrape` → Get `task_id`
2. **Monitor Progress** → Poll `GET /scraping_status` → Get `percentage`
3. **Stop if Needed** → Call `POST /stop_scraping_work` → Get `urls_processed`
4. **Validate Data** → Call `POST /validate` → Get `validation` report
5. **Auto-Fix Issues** → Call `POST /validate-fix` → Get `fix` task_id

### HTTP Request Nodes
Use n8n **HTTP Request** node with:
- **Method**: GET or POST
- **URL**: `https://<your-railway-domain>/<endpoint>`
- **Headers**: `Content-Type: application/json` (for POST)

## Testing

### Test Health Check
```bash
curl http://<railway-domain>/health_check
```

### Test Start Bulk
```bash
curl -X POST http://<railway-domain>/start_bulk_scrape
```

### Test Status Check
```bash
curl http://<railway-domain>/scraping_status
```

## Architecture Notes

### Concurrency
- Multiple tasks can run simultaneously
- Each endpoint creates background task
- Worker state is thread-safe (async)

### Error Handling
- All endpoints catch and log exceptions
- Return 500 status on internal errors
- Return 503 if worker not initialized
- Return 409 if bulk scrape already running

### Memory Management
- Browser contexts isolated per URL
- Browser restart every 30 URLs
- Pages/contexts always closed after use
- No memory leaks from Playwright

## Next Steps

1. **Deploy to Railway** - Build in progress
2. **Verify endpoints** - Test each endpoint works
3. **Check logs** - Monitor for any errors
4. **Set Railway domain** - Get stable URL for n8n
5. **Test n8n integration** - Connect workflows to API

## Files Changed Summary

```
api.py                          (NEW - 380 lines)
main.py                          (MODIFIED - bulk task tracking)
modules/scraper.py              (MODIFIED - browser restart)
requirements.txt                 (MODIFIED - +2 packages)
Dockerfile                       (MODIFIED - expose port, health check)
```

Total lines added: ~400
Total lines modified: ~50
