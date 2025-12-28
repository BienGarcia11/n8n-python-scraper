# Railway Bulk Scraper Setup Guide

## 🎯 Overview

**Solution:** Your Railway project already has bulk scraping integrated. The bulk scraper is part of `api_server.py` at endpoint `/scrape/bulk`.

**What this means:**
- ✅ n8n triggers bulk scraping via HTTP call
- ✅ Railway processes all pending URLs in background
- ✅ n8n continues working without lag
- ✅ Runs automatically every 2 weeks (scheduled)
- ✅ Works even when you're away

---

## 📋 Architecture

```
n8n Workflow (Schedule Trigger)
    ↓
Trigger Bulk Scrape (HTTP Request)
    ↓ POST /scrape/bulk
Railway Service (api_server.py)
    ↓
1. Fetch pending URLs from Supabase
2. Scrape in batches (3 URLs, 2 concurrent)
3. Generate OpenAI embeddings
4. Insert to documents table
5. Update URL status to completed
    ↓
Check Railway logs for real-time progress
    ↓
Content immediately searchable in RAG chat system
```

---

## 🔧 Step 1: Deploy to Railway

### 1.1 Verify Files

Make sure you have these files:
- ✅ `api_server.py` - Contains `/scrape/bulk` endpoint
- ✅ `scraper.py` - Scraper functions
- ✅ `requirements.txt` - Dependencies
- ✅ `Dockerfile` - Railway build config
- ✅ `railway.toml` - Railway project config

### 1.2 Link to Railway (if not already)

```bash
cd "c:\Coding Projects\n8n Google Antigravity\RAG System with Semantic Cache"
railway link
```

Select your Railway project: "n8n python scraper"

### 1.3 Deploy

```bash
railway up
```

Railway will:
- Build the Docker container
- Deploy `api_server.py` (includes bulk scraper)
- Provide a public URL

**Example URL:** `https://n8n-python-scraper-production.up.railway.app`

---

## 🔑 Step 2: Configure Environment Variables

Go to Railway Dashboard → Your Project → **Settings** → **Variables**

Add these:

| Name | Value |
|-------|--------|
| `SUPABASE_URL` | `https://ykohyrwipxpwztptfopi.supabase.co` |
| `SUPABASE_KEY` | Your Supabase service role key |
| `OPENAI_API_KEY` | Your OpenAI API key |

### Get Your Keys:

**Supabase Service Role Key:**
1. Go to: https://supabase.com/dashboard/project/ykohyrwipxpwztptfopi/settings/api
2. Scroll to **Project API keys**
3. Copy `service_role` key

**OpenAI API Key:**
1. Go to: https://platform.openai.com/api-keys
2. Click **Create new secret key**
3. Copy the key

---

## 🚀 Step 3: Test Bulk Scraping

### 3.1 Test via n8n

1. Open your n8n workflow: **"OpenAI Question Answering Workflow With Semantic Cache"**
2. Find node: **"Trigger Bulk Scrape"** (HTTP Request)
3. Verify URL:
   ```
   https://n8n-python-scraper-production.up.railway.app/scrape/bulk
   ```
4. Test the node by clicking **"Execute Node"**
5. Expected response:

```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "started",
  "pending_count": 45,
  "message": "Started bulk scraping 45 URLs",
  "note": "This task runs asynchronously. Check Railway logs for progress."
}
```

### 3.2 Watch Railway Logs

1. Go to Railway Dashboard
2. Click your scraper service
3. **Logs** tab shows real-time progress:

```
============================================================
BULK SCRAPE TASK: 123e4567-e89b-12d3-a456-426614174000
============================================================
Pending URLs: 45
Batch size: 3
Total batches: 15

BATCH 1/15: 3 URLs
  ✓ https://example.com/page1...
  ✓ https://example.com/page2...
  ✓ https://example.com/page3...
Batch 1 complete: 3 processed
Progress: 6.7% (3/45)

[Continues...]

============================================================
BULK SCRAPE COMPLETE
============================================================
Total: 45
Success: 42
Failed: 3
Success rate: 93.3%
```

### 3.3 Verify in Supabase

After scraping completes, check database:

```sql
-- View completed URLs
SELECT url, title, status, updated_at
FROM url_queue
WHERE status = 'completed'
ORDER BY updated_at DESC
LIMIT 50;

-- View imported documents
SELECT 
  metadata->>'title' as title,
  metadata->>'source' as url,
  metadata->>'scraped_at' as scraped_at
FROM documents
WHERE metadata->>'source_type' = 'web_scrape'
ORDER BY created_at DESC
LIMIT 20;
```

---

## ⏰ Step 4: Set Up Bi-Weekly Automation

### 4.1 Add Schedule Trigger to n8n Workflow

1. Open your n8n workflow
2. Add **Schedule Trigger** node (or find existing one)
3. Configure:

**Cron Expression for Every 2 Weeks:**
```
0 2 * * 1,15
```

This runs:
- At 2:00 AM
- On the 1st and 15th of every month
- Effectively every 2 weeks

**Alternative - Every Sunday:**
```
0 2 * * 0
```

This runs:
- Every Sunday at 2:00 AM (weekly)

### 4.2 Connect Workflow

Connect the nodes in this order:

```
Schedule Trigger (every 2 weeks)
    ↓
Trigger Bulk Scrape (HTTP Request)
    ↓
Bulk Scrape Complete (No-op node)
```

### 4.3 Activate Workflow

Click **"Active"** toggle in n8n to enable automatic execution.

**Result:** Every 2 weeks at 2:00 AM, n8n will trigger Railway bulk scraping, which processes all pending URLs and imports them to your RAG system.

---

## 📊 Monitoring & Maintenance

### Daily/Weekly Checks

**1. Check Railway Logs**
- Go to Railway Dashboard → Service → Logs
- Look for any errors or crashes
- Monitor success rate

**2. Check Failed URLs**

```sql
-- View failed URLs
SELECT url, status, updated_at
FROM url_queue
WHERE status = 'failed'
ORDER BY updated_at DESC
LIMIT 20;

-- Reset failed URLs (if you want to retry)
UPDATE url_queue SET status = 'pending' WHERE status = 'failed';
```

**3. Add New URLs**
- Run sitemap import workflow
- Or manually insert URLs:

```sql
INSERT INTO url_queue (url, status) VALUES
  ('https://example.com/page1', 'pending'),
  ('https://example.com/page2', 'pending');
```

### Verify RAG System

After bulk scraping completes, test your RAG chat system:

1. Ask a question about the newly scraped content
2. Verify it returns relevant results
3. Confirm embeddings are working correctly

---

## 🔧 Troubleshooting

### Issue: "SUPABASE_KEY not configured"

**Solution:**
1. Go to Railway Dashboard → Settings → Variables
2. Add `SUPABASE_KEY` with your service role key
3. Redeploy: `railway up`

### Issue: No pending URLs found

**Solution:**
Add URLs to queue first:

```sql
INSERT INTO url_queue (url, status) VALUES
  ('https://example.com/page1', 'pending');
```

Or run your sitemap import workflow to add URLs from a sitemap.

### Issue: Railway logs show browser crash

**Solution:**
Reduce concurrency in `api_server.py`:

```python
# Line ~50
semaphore = asyncio.Semaphore(1)  # Reduce from 2 to 1
```

Redeploy:
```bash
railway up
```

### Issue: "Failed to generate embeddings"

**Cause:** Missing or invalid OpenAI API key

**Solution:**
1. Add `OPENAI_API_KEY` to Railway variables
2. Verify key has credits: https://platform.openai.com/usage

**Note:** Without embeddings, documents are still inserted but won't be searchable in RAG.

### Issue: URLs stuck in "processing" status

**Cause:** Railway service restarted during scraping

**Solution:**
Reset in Supabase:
```sql
UPDATE url_queue SET status = 'pending' WHERE status = 'processing';
```

Then trigger bulk scrape again from n8n.

### Issue: n8n shows HTTP error

**Common causes:**
1. Wrong Railway URL
2. Railway service not running
3. Railway redeploying

**Solution:**
1. Verify URL in n8n: `https://your-url.up.railway.app/scrape/bulk`
2. Check Railway service is running (green status)
3. Check Railway logs for errors

---

## 📈 Performance Tuning

### Free Tier (512MB RAM) - Recommended

```python
# api_server.py - Line ~50
semaphore = asyncio.Semaphore(2)  # 2 concurrent
batch_size = 3  # 3 URLs per batch (in bulk function)
```

**Expected:** ~100 URLs/hour

### Paid Tier (1GB+ RAM)

```python
# api_server.py - Line ~50
semaphore = asyncio.Semaphore(5)  # 5 concurrent
batch_size = 10  # 10 URLs per batch
```

**Expected:** ~300 URLs/hour

### How to Adjust

Edit `api_server.py`:

```python
# Line ~460 (bulk scrape function)
batch_size = 5  # Change this value

# Line ~50 (global)
semaphore = asyncio.Semaphore(2)  # Change this value
```

Then redeploy:
```bash
railway up
```

---

## 🔐 Security Notes

### Environment Variables

- ✅ **Railway Variables** - Secure (encrypted at rest)
- ❌ **Never commit** keys to Git
- ❌ **Never share** Railway dashboard URL publicly

### Service Role Key

Use Supabase **service role** key:
- Has full write permissions
- Bypasses RLS policies
- Only use in trusted services (Railway, not public web apps)

---

## 📅 Recommended Workflow

### Weekly Maintenance (5 minutes)

1. Check Railway logs for errors
2. Check failed URLs in Supabase
3. Add new URLs via sitemap or manual insert
4. Test RAG chat system

### Bi-Weekly (Automatic)

**What happens automatically:**
1. n8n schedule triggers at 2:00 AM
2. Calls Railway `/scrape/bulk` endpoint
3. Railway fetches all pending URLs
4. Scrapes in batches with embeddings
5. Updates Supabase with completed documents
6. Content is searchable in RAG

**No manual intervention needed!**

---

## 🆘 Emergency Recovery

### If Railway Service Crashes

1. Check logs to identify error
2. Reset stuck URLs:
```sql
UPDATE url_queue SET status = 'pending' WHERE status = 'processing';
```
3. Redeploy:
```bash
railway up
```
4. Trigger bulk scrape from n8n

### If OpenAI Embeddings Fail

Documents are still inserted without embeddings:

```sql
-- Find documents without embeddings
SELECT metadata->>'title', metadata->>'source'
FROM documents
WHERE metadata->>'no_embedding' = 'true'
LIMIT 20;
```

**Regenerate embeddings:**
```python
# Run locally (if needed)
python bulk_scrape_import.py --batch-size 50
```

---

## ✅ Checklist

- [ ] Deploy to Railway: `railway up`
- [ ] Configure environment variables in Railway
- [ ] Test `/scrape/bulk` endpoint via n8n
- [ ] Watch Railway logs for progress
- [ ] Verify URLs in Supabase after completion
- [ ] Query RAG chat system to test searchable content
- [ ] Add schedule trigger to n8n workflow
- [ ] Set cron: `0 2 * * 1,15` (every 2 weeks)
- [ ] Activate workflow in n8n
- [ ] Monitor Railway logs periodically

---

## 🎯 Success Indicators

✅ **When it's working:**
- n8n schedule triggers successfully
- Railway logs show batches processing
- URLs marked as "completed" in Supabase
- Content appears in `documents` table with embeddings
- RAG chat system can query new content

❌ **If something's wrong:**
- n8n shows error on HTTP request
- Railway logs show browser crashes
- URLs stuck in "processing" status
- No new documents in Supabase
- RAG chat doesn't find newly scraped content

---

## 📞 Quick Commands

### Check Railway Health
```bash
curl https://your-url.up.railway.app/health
```

### Test Bulk Endpoint
```bash
curl -X POST https://your-url.up.railway.app/scrape/bulk
```

### Reset Stuck URLs
```sql
UPDATE url_queue SET status = 'pending' WHERE status = 'processing';
```

### View Failed URLs
```sql
SELECT url, updated_at FROM url_queue WHERE status = 'failed' LIMIT 20;
```

---

**Your automated bulk scraping system is ready!** 🚀

It will run automatically every 2 weeks, scrape all pending URLs from Railway, and import them to your RAG system - even when you're away from home.

---

## 📚 Related Documentation

- **Railway Deployment Guide.md** - General Railway setup
- **N8N Workflow Update Instructions.md** - n8n workflow details
- **BULK_SCRAPE_GUIDE.md** - Local bulk scraping (alternative)
