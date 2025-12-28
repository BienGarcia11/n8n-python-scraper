# N8N Bulk Scraper Control - Setup Guide

## 📋 Overview

This n8n workflow provides complete automation and control for your Railway bulk scraper. It includes:

- **Scheduled Execution**: Runs every 2 weeks automatically
- **Progress Monitoring**: Checks status after starting
- **Smart Completion Detection**: Validates HTTP response codes
- **Emergency Stop**: Can cancel running bulk scrape
- **Error Handling**: Logs and notifies on failures

---

## 🚀 Railway Endpoints Used

| Endpoint | Method | Purpose |
|----------|---------|---------|
| `/scrape/bulk` | POST | Start bulk scraping |
| `/scrape/bulk/status` | GET | Check progress/status |
| `/scrape/bulk/stop` | POST | Stop running job |

**Base URL**: `http://n8n-python-scraper-production.up.railway.app`

---

## 📥 Workflow Nodes

### 1. Schedule Trigger
- **Purpose**: Automatically trigger workflow every 2 weeks
- **Node Type**: `n8n-nodes-base.scheduleTrigger`
- **Configuration**:
  - **Cron Expression**: `0 2 * * 1`
    - Runs every 2 weeks on Mondays at 2:00 AM
  - **Mode**: `trigger` (start new execution)

### 2. Start Bulk Scrape
- **Purpose**: Trigger bulk scrape on Railway
- **Node Type**: `n8n-nodes-base.httpRequest`
- **Method**: `POST`
- **URL**: `http://n8n-python-scraper-production.up.railway.app/scrape/bulk`
- **Configuration**:
  - **Send Body**: Yes
  - **Headers**: Default
  - **Query**: None
  - **Body Spec**: None
  - **Continue On Fail**: No

### 3. Check Success
- **Purpose**: Verify bulk scrape started successfully
- **Node Type**: `n8n-nodes-base.if`
- **Condition**: HTTP Status Code equals `200` OR `299`
- **Combine Operation**: Any
- **Configuration**:
  - **Left Value**: Empty
  - **Type Validation**: Strict
  - **Value 1**: `200`
  - **Value 2**: `299`

### 4. Monitor Status
- **Purpose**: Get current progress of bulk scrape
- **Node Type**: `n8n-nodes-base.httpRequest`
- **Method**: `GET`
- **URL**: `http://n8n-python-scraper-production.up.railway.app/scrape/bulk/status`
- **Configuration**:
  - **Send Body**: No
  - **Headers**: Default
  - **Query**: None
  - **Body Spec**: None

### 5. Is Running?
- **Purpose**: Check if bulk scrape is currently active
- **Node Type**: `n8n-nodes-base.if`
- **Condition**: HTTP Status Code equals `200` OR `299`
- **Combine Operation**: Any

### 6. Log Status
- **Purpose**: Store status, task ID, and progress
- **Node Type**: `n8n-nodes-base.set`
- **Assignments**:
  - **status**: `{{ $json.status }}`
  - **task_id**: `={{ $json.task_id }}`
  - **progress**: `={{ $json.progress }}%`

### 7. Progress ≥ 80%?
- **Purpose**: Check if scraping is 80% complete
- **Node Type**: `n8n-nodes-base.if`
- **Condition**: Progress ≥ 80%
- **Configuration**:
  - **Left Value**: Empty
  - **Type Validation**: Strict
  - **Value 1**: `80`

### 8. Final Status Check
- **Purpose**: Get final status before completion
- **Node Type**: `n8n-nodes-base.httpRequest`
- **Method**: `GET`
- **URL**: `http://n8n-python-scraper-production.up.railway.app/scrape/bulk/status`
- **Configuration**:
  - **Send Body**: No
  - **Headers**: Default
  - **Query**: None
  - **Body Spec**: None

### 9. Set Success Message
- **Purpose**: Prepare success notification
- **Node Type**: `n8n-nodes-base.set`
- **Assignments**:
  - **status**: `Bulk scrape completed successfully!`
  - **task_id**: `={{ $json.task_id }}`
  - **progress**: `100%`

### 10. Error: Not ≥ 80%
- **Purpose**: Error handling if progress never reached 80%
- **Node Type**: `n8n-nodes-base.if`
- **Condition**: Progress < 80% (NOT reached threshold)
- **Combine Operation**: All conditions must fail

### 11. Emergency Stop
- **Purpose**: Cancel running bulk scrape immediately
- **Node Type**: `n8n-nodes-base.httpRequest`
- **Method**: `POST`
- **URL**: `http://n8n-python-scraper-production.up.railway.app/scrape/bulk/stop`
- **Configuration**:
  - **Send Body**: Yes
  - **Headers**: Default
  - **Query**: None
  - **Body Spec**: None

### 12. Log Error
- **Purpose**: Store error details if stop fails
- **Node Type**: `n8n-nodes-base.set`
- **Assignments**:
  - **error_status**: `Bulk scrape stopped or failed`
  - **error_message**: `={{ $json.message }}`

### 13. Is Stopped/Not Running?
- **Purpose**: Check if scraper stopped or never started
- **Node Type**: `n8n-nodes-base.if`
- **Condition**: Status is "stopped" OR "not_running"
- **Combine Operation**: Any

### 14. Prepare Notification
- **Purpose**: Format notification message
- **Node Type**: `n8n-nodes-base.set`
- **Assignments**:
  - **notification_title**: `Bulk Scraper: {{ $json.error_status }}`
  - **notification_message**: `{{ $json.error_message }}`

---

## 📊 Workflow Flow

```
Schedule Trigger
    ↓
Start Bulk Scrape
    ↓
[HTTP 200/299?]
    ↓ (TRUE)  Monitor Status
    ↓                ↓ (TRUE) Log Status
    ↓                    ↓ (TRUE) Is Running?
    ↓                        ↓ (TRUE) Progress ≥ 80%?
    ↓                            ↓ (TRUE) Final Status Check
    ↓                                    ↓ (TRUE) Set Success Message
    ↓                                    ↓ (FALSE)
    ↓ (FALSE) Emergency Stop
    ↓                        ↓ (FALSE) Log Error
    ↓                                    ↓ (FALSE) Is Stopped/Not Running?
    ↓                                            ↓ (TRUE) Prepare Notification
```

---

## 🔧 How to Import Workflow

### Option 1: Import JSON File

1. Open your n8n instance
2. Go to **Workflows** → **Import from File**
3. Click **"Import from File"**
4. Select `Bulk Scraper Control Workflow.json` from your project directory
5. Click **Import**

### Option 2: Paste JSON

1. Create new workflow in n8n
2. Go to **...** (top right menu) → **"Import from File"** → **"Paste from JSON"**
3. Paste the entire JSON content from `Bulk Scraper Control Workflow.json`
4. Click **"Import"**

---

## ⚙️ Configuration Steps

### 1. Update Railway URL (if different)

If your Railway URL is different from `http://n8n-python-scraper-production.up.railway.app`:

1. Find **"Start Bulk Scrape"** node (HTTP Request)
2. Click to expand
3. In **URL** field, replace with your actual Railway URL
4. Save

### 2. Adjust Schedule (Optional)

Change the bi-weekly schedule:

1. Find **"Schedule Trigger"** node
2. Change **Cron Expression**:
   - Daily: `0 2 * * *` (every 2 hours)
   - Weekly: `0 2 * * 1` (every Monday at 2 AM)
   - Monthly: `0 2 1 *` (first of month)
   - Custom: Use https://crontab.guru/ to build

### 3. Add Notification (Optional)

To receive notifications when bulk scrape completes:

1. Add a notification node after **"Set Success Message"** node
2. Connect to your preferred channel (Slack, Telegram, Email, Discord)

---

## 🧪 Testing the Workflow

### Test 1: Manual Trigger

1. Open workflow
2. Click **"Test workflow"** (play button)
3. Verify:
   - HTTP Request executes successfully
   - Returns task ID
   - Status is logged

### Test 2: Check Status

1. Copy the **"Monitor Status"** node
2. Test it separately
3. Verify you get JSON with running status:
   ```json
   {
     "running": true,
     "task_id": "...",
     "progress": 45.5
   }
   ```

### Test 3: Emergency Stop

1. Copy the **"Emergency Stop"** node
2. Test it separately
3. Verify bulk scraper stops:
   ```json
   {
     "status": "stopped",
     "message": "Bulk scraper stopped after current batch completes"
   }
   ```

---

## 📈 Railway API Responses

### Start Bulk Scrape Response

**Success (job started):**
```json
{
  "task_id": "abc-123-def...",
  "status": "started",
  "pending_count": 45,
  "message": "Started bulk scraping 45 URLs",
  "safety_limit": "Max 100 URLs per run",
  "note": "This task runs asynchronously. Check Railway logs for progress."
}
```

**No URLs to process:**
```json
{
  "task_id": "...",
  "status": "completed",
  "pending_count": 0,
  "message": "No pending URLs to scrape"
}
```

**Already running:**
```json
{
  "status": "already_running",
  "task_id": "abc-123...",
  "message": "Bulk scraper is already running. Use GET /scrape/bulk/status to check progress.",
  "stop_command": "POST /scrape/bulk/stop to cancel"
}
```

### Status Check Response

**Running:**
```json
{
  "running": true,
  "task_id": "abc-123-def...",
  "started_at": "2025-12-28T09:00:00",
  "total_urls": 45,
  "processed": 15,
  "failed": 2,
  "progress": 37.8,
  "cancelled": false,
  "stop_command": "POST /scrape/bulk/stop to cancel"
}
```

**Not running:**
```json
{
  "running": false,
  "message": "No bulk scrape task is currently running",
  "start_command": "POST /scrape/bulk to start"
}
```

### Stop Response

**Successfully stopped:**
```json
{
  "status": "stopped",
  "message": "Bulk scraper stopped after current batch completes",
  "summary": {
    "task_id": "abc-123...",
    "total_urls": 45,
    "processed": 15,
    "failed": 2,
    "progress": 37.8
  },
  "note": "URLs in 'processing' status will remain and can be retried"
}
```

**No task running:**
```json
{
  "status": "not_running",
  "message": "No bulk scrape task is currently running"
}
```

---

## 🛡️ Safety Features

### Automatic Safety Controls

1. **Duplicate Prevention**: Won't start if job already running
2. **Maximum URLs**: 100 URLs per run (configurable in `api_server.py`)
3. **Batch Processing**: 3 URLs per batch
4. **Concurrent Limit**: 2 requests at once
5. **Browser Restart**: Every 50 requests (memory management)

### Emergency Stop Options

1. **Via n8n**: Use "Emergency Stop" node in workflow
2. **Via Railway**: Manual `POST /scrape/bulk/stop` HTTP request
3. **Via Dashboard**: Click **"Redeploy"** in Railway (forces restart)
4. **Via CLI**: `railway down` (if Railway CLI is installed)

---

## 📝 Integration with Existing Workflow

### Add to "OpenAI Question Answering Workflow With Semantic Cache"

1. Open your existing workflow
2. Find the node that adds URLs to database
3. Replace or add after it:
   - Add **"Start Bulk Scrape"** node reference
   - Or add a new branch: Bulk Scrape → Status Check

4. Connect the workflow:
   ```
   [URL addition] → [Wait 1 min] → [Start Bulk Scrape]
   ```

---

## 🚨 Troubleshooting

### "Bulk scrape completed successfully!" but 0% progress

**Cause**: Railway returned HTTP 200 but had 0 URLs to process

**Solution**: 
- Check Supabase `url_queue` table has URLs with `status = 'pending'`
- Check Railway environment variables are set

### "already_running" error

**Cause**: Trying to start while previous job is still active

**Solution**: 
- Wait for previous job to complete
- Use `GET /scrape/bulk/status` to check progress
- Use `POST /scrape/bulk/stop` to cancel

### HTTP Request fails

**Common errors**:
- **Connection refused**: Railway service may be down
- **Timeout**: Railway instance might be restarting
- **429/500 errors**: Temporary API issues

**Debug steps**:
1. Test endpoint directly with curl:
   ```powershell
   curl http://n8n-python-scraper-production.up.railway.app/scrape/bulk/status
   ```
2. Check Railway logs for errors
3. Verify service is running (health check)

---

## 📊 Monitoring Best Practices

### Using Railway Logs

1. Go to Railway Dashboard → Service → **Logs** tab
2. Watch for progress markers:
   ```
   BULK SCRAPE TASK: abc-123...
   Pending URLs: 45
   Safety limit: 100 URLs per run
   
   BATCH 1/15: 3 URLs
     ✓ https://example.com/page1...
     ✓ https://example.com/page2...
     ✓ https://example.com/page3...
   Batch 1 complete: 3 processed
   
   BULK SCRAPE COMPLETE: abc-123...
   Total: 45
   Success: 40
   Failed: 5
   Success rate: 88.9%
   ```

### Progress Tracking

Use n8n expressions to track progress:
- `$json.total_urls` - Total URLs to process
- `$json.processed` - URLs successfully scraped
- `$json.progress` - Current progress percentage
- `$json.task_id` - Current job identifier

---

## 🔐 Security Notes

1. **HTTPS vs HTTP**: Railway should use HTTPS. If `http://` doesn't work, try `https://`
2. **CORS**: Railway scraper accepts all origins (no authentication)
3. **Rate Limiting**: No built-in rate limiting (controlled by Railway)
4. **API Keys**: Stored securely in Railway environment variables (never in workflow)

---

## 📚 Additional Resources

### Railway Documentation
- https://docs.railway.com
- Project Management, Service Configuration, Logs, Monitoring

### Cron Expression Generator
- https://crontab.guru/
- Build and test cron expressions

### n8n Expression Syntax
- `$json.field` - Access JSON fields
- `{{ $node-name.json.field }}` - Access previous node's output

---

## ✅ Setup Checklist

Before activating the workflow:

- [ ] Import workflow JSON into n8n
- [ ] Verify Railway URL is correct (test with curl first)
- [ ] Configure schedule timing (every 2 weeks recommended)
- [ ] Test manual trigger (verify bulk scrape starts)
- [ ] Test status monitoring (verify progress tracking)
- [ ] Test emergency stop (verify cancellation works)
- [ ] Add notification node (optional - for alerts)
- [ ] Check Railway logs during first run
- [ ] Verify all URLs are processed successfully
- [ ] Integrate with existing RAG workflow (optional)
- [ ] Activate workflow in production mode
- [ ] Document any customizations

---

## 🎯 Quick Start Commands

### Test Railway Endpoints (PowerShell)

```powershell
# Check if service is running
curl http://n8n-python-scraper-production.up.railway.app/scrape/bulk/status

# Start bulk scrape
Invoke-RestMethod -Uri "http://n8n-python-scraper-production.up.railway.app/scrape/bulk" -Method POST

# Stop running scrape
Invoke-RestMethod -Uri "http://n8n-python-scraper-production.up.railway.app/scrape/bulk/stop" -Method POST
```

### Test Railway Endpoints (cURL)

```bash
# Check status
curl http://n8n-python-scraper-production.up.railway.app/scrape/bulk/status

# Start bulk scrape
curl -X POST http://n8n-python-scraper-production.up.railway.app/scrape/bulk

# Stop bulk scrape
curl -X POST http://n8n-python-scraper-production.up.railway.app/scrape/bulk/stop
```

---

## 💡 Customization Ideas

### Add Manual Trigger

Add a manual trigger node at the start for on-demand scraping:

1. Add **"Manual Trigger"** node
2. Connect: Manual Trigger → Start Bulk Scrape
3. Allows running bulk scrape anytime, not just on schedule

### Add Progress Dashboard

Create a visual progress display using n8n:

1. After Start Bulk Scrape, add a loop that polls status every 30 seconds
2. Display: Total URLs, Processed, Failed, Progress %
3. Stop when running: false OR progress = 100%

### Add Email Report

Generate a summary email after completion:

1. After Set Success Message, add Email node
2. Subject: "Bulk Scrape Complete - {{ $json.task_id }}"
3. Body:
   ```
   Task ID: {{ $json.task_id }}
   Total URLs: {{ $json.total_urls }}
   Success: {{ $json.processed }}
   Failed: {{ $json.failed }}
   Success Rate: {{ $json.progress }}%
   ```

### Add Multi-Queue Support

If you want to manage multiple URL queues:

1. Add a Set node before Start Bulk Scrape
2. Set `queue_name` variable (e.g., "priority", "research", "news")
3. Pass this to Railway scraper via query parameter (requires API modification)

---

## 🆘 Support & Issues

### Common Problems

| Problem | Solution |
|---------|----------|
| Railway service not responding | Check Railway Dashboard → Logs for errors |
| HTTP 429/500 errors | Wait and retry, check Railway status |
| Progress stuck at same % | May have duplicate URLs with same content |
| URLs marked "processing" stuck | Manually reset status in Supabase |

### Getting Help

1. Check Railway logs for specific error messages
2. Verify Railway environment variables are set
3. Test endpoints directly with curl
4. Review this workflow's connections for proper flow

---

## 📄 Document Version

- **Version**: 1.0
- **Created**: 2025-12-28
- **Railway URL**: `http://n8n-python-scraper-production.up.railway.app`
- **Compatible n8n Version**: 1.0.0+

---

**Your bulk scraper automation is ready to use!** 🚀
