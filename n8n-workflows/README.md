# n8n Workflow Templates

Pre-configured n8n workflows for all RAG Scraper API endpoints.

## Quick Import

1. Open n8n workflow editor
2. Click "Import from File"
3. Select the desired `.json` file from this directory

## Available Workflows

### 1. Health Check (`01_health_check.json`)
- **Endpoint**: `GET /health_check`
- **Schedule**: Every 5 minutes (automated)
- **Purpose**: Monitor scraper service health
- **Use Case**: Continuous monitoring to ensure service is running and browser is warm

**Response**:
- `status`: "healthy" or "unhealthy"
- `browser_warm`: "warm" or "cold"
- `requests_processed`: Total URLs processed
- `service_uptime`: How long service has been running

---

### 2. Scraping Status (`02_scraping_status.json`)
- **Endpoint**: `GET /scraping_status`
- **Trigger**: Manual only
- **Purpose**: Get current bulk scrape progress
- **Use Case**: Monitor progress without waiting for completion

**Response**:
- `task_id`: Unique task identifier
- `status`: "idle", "running", "completed", or "error"
- `total_urls`: Total URLs in queue
- `processed_urls`: URLs successfully processed
- `failed_urls`: URLs that failed
- `percentage`: Completion percentage (0-100)

---

### 3. Start Bulk Scrape (`03_start_bulk_scrape.json`)
- **Endpoint**: `POST /start_bulk_scrape`
- **Trigger**: Manual only
- **Purpose**: Start scraping all pending URLs
- **Use Case**: Begin full scraping job when new URLs are added

**Response**:
- `task_id`: Unique task identifier
- `status`: "started"
- `queued_urls`: Number of URLs queued for processing

**Behavior**:
- Scrapes all URLs with status 'pending'
- Processes URLs in batches for efficiency
- Runs in background (returns immediately)
- Can be monitored via `/scraping_status`
- Can be stopped via `/stop_scraping_work`

---

### 4. Stop Scraping Work (`04_stop_scraping_work.json`)
- **Endpoint**: `POST /stop_scraping_work`
- **Trigger**: Manual only
- **Purpose**: Gracefully stop currently running bulk scrape
- **Use Case**: Pause or restart scraping with different settings

**Response**:
- `status`: "stopping"
- `urls_processed`: Number of URLs processed before stop
- `message`: Confirmation message

**Behavior**:
- Waits for current URL to finish (max 30 seconds)
- Does not delete processed data
- Already-processed URLs remain in database

---

### 5. Validate URLs (`05_validate_urls.json`)
- **Endpoint**: `POST /validate`
- **Trigger**: Manual only
- **Purpose**: Check data consistency across URL queue and documents
- **Use Case**: Identify issues before running validate-fix

**Response**:
- `total_urls`: Total URLs in queue
- `success_rate`: Percentage (0-100)
- `total_issues`: Number of issues found
- `issues.stuck_processing`: URLs stuck in 'processing' > 3 minutes
- `issues.missing_documents`: Completed URLs without documents
- `issues.failed_urls`: URLs that failed to scrape
- `failed_urls`: List of up to 50 failed URLs with details

**Performance**:
- Uses batch lookups (83x faster than 1-by-1)
- Handles unlimited URLs (1K, 10K, 100K, 1M+)
- Returns in seconds for 5K URLs

---

### 6. Validate and Fix (`06_validate_and_fix.json`)
- **Endpoint**: `POST /validate-fix`
- **Trigger**: Manual only
- **Purpose**: Automatically fix data consistency issues
- **Use Case**: Fix issues identified by `/validate`

**Response**:
- `task_id`: Unique task identifier
- `status`: "fixing"
- `issues_found`: Number of issues detected
- `fixed_urls`: Number of URLs fixed (updates as task runs)

**Auto-Fixes**:
- ✅ **Stuck processing URLs**: Reset to 'pending', clear errors, reset attempts
- ✅ **Missing documents**: Completed URLs without docs reset to 'pending'
- ✅ **Failed URLs**: Reset to 'pending' for retry (transient failures may succeed on retry)

**Behavior**:
- Runs in background (returns immediately)
- Processes URLs in batches for efficiency
- Can monitor progress via logs
- Uses pagination for unlimited URLs
- Optimized batch lookups (100x faster)

---

## Typical Workflow

### Bulk Scraping
1. Add URLs to `url_queue` table in Supabase
2. Import & run **03_start_bulk_scrape.json** (Start Bulk Scrape)
3. Import & run **02_scraping_status.json** (Scraping Status) to monitor progress
4. Wait for completion (or stop early with **04_stop_scraping_work.json**)

### Data Validation & Repair
1. Import & run **05_validate_urls.json** (Validate URLs) to check for issues
2. Review validation report (stuck, missing documents, failed URLs)
3. Import & run **06_validate_and_fix.json** (Validate and Fix) to auto-fix issues
4. Check logs for fix progress
5. Optionally, manually review and re-add failed URLs

### Monitoring
1. Import **01_health_check.json** (Health Check)
2. Enable workflow for continuous monitoring (every 5 minutes)
3. Review health status in n8n workflow history

---

## API Base URL

```
https://n8n-python-scraper-production.up.railway.app
```

## Notes

- All workflows use unique node IDs for easy import
- Sticky notes provide inline documentation
- No credentials required (public API endpoints)
- Background tasks return task IDs for tracking
- Validation endpoints are optimized for unlimited URL counts
