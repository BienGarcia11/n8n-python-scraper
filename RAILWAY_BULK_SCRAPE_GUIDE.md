# Railway Bulk Scraping Setup Guide

## 🎯 Overview

**Solution:** Trigger bulk scraping from n8n → Railway processes URLs in background → n8n continues working

This setup allows:
- ✅ Automated bi-weekly bulk scraping (even when you're away)
- ✅ n8n doesn't lag or crash during scraping
- ✅ Railway handles long-running tasks (500+ URLs)
- ✅ Monitor progress via Railway logs
- ✅ All URLs properly tracked and marked as completed

---

## 📋 Architecture

```
n8n Workflow (Schedule Trigger)
    ↓
Trigger Bulk Scrape (HTTP Request)
    ↓ POST /scrape/bulk
Railway Service (Background Task)
    ↓
Scrape all pending URLs → Insert to RAG
    ↓
Check Railway logs for progress
```

---

## 🔧 Step 1: Deploy to Railway

### 1.1 Link Railway Project

If not already linked:

```bash
cd "c:\Coding Files\n8n Google Antigravity\RAG System with Semantic Cache"
railway link
```

Select or create your Railway project.

### 1.2 Configure Environment Variables

Set these in Railway (Settings → Variables):

```bash
SUPABASE_URL=https://ykohyrwipxpwztptfopi.supabase.co
SUPABASE_KEY=your-service-role-key
OPENAI_API_KEY=sk-your-openai-api-key
```

### 1.3 Deploy

```bash
railway up
```

Railway will:
- Build the Dockerfile
- Deploy the API server
- Start the service on a public URL

### 1.4 Get Your Railway URL

After deployment, Railway will provide:
```
https://your-project-name-production.up.railway.app
```

**Example:** `https://n8n-python-scraper-production.up.railway.app`

---

## 🚀 Step 2: Test Bulk Scraping Endpoint

### 2.1 Test via n8n

1. Open your n8n workflow: "OpenAI Question Answering Workflow With Semantic Cache"
2. Find the new node: **"Trigger Bulk Scrape"** (HTTP Request)
3. Verify the URL is your Railway URL: `https://your-url.up.railway.app/scrape/bulk`
4. Test the node:

```json
{
  "task_id": "uuid-here",
  "status": "started",
  "pending_count": 45,
  "message": "Started bulk scraping 45 URLs",
  "note": "This task runs asynchronously. Check Railway logs for progress."
}
```

### 2.2 Test via curl (Optional)

```bash
curl -X POST https://your-url.up.railway.app/scrape/bulk
```

### 2.3 Monitor in Railway

1. Go to Railway project
2. Click your scraper service
3. **Logs tab** → Watch real-time scraping progress
4. You'll see:

```
============================================================
BULK SCRAPE TASK: 123e4567-e89b-12d3-a456-426614174000
============================================================
Pending URLs: 45

BATCH 1/15: 3 URLs
  ✓ https://example.com/page1...
  ✓ https://example.com/page2...
  ✓ https://example.com/page3...
Batch 1 complete: 3 success

[Continues...]

============================================================
BULK SCRAPE COMPLETE: 123e4567-e89b-12d3-a456-426614174000
============================================================
Total: 45
Success: 42
Failed: 3
Success rate: 93.3%
```

---

## ⏰ Step 3: Configure Bi-Weekly Scheduling

### Option A: Use n8n Schedule Trigger

1. Open your n8n workflow
2. Find or create a **Schedule Trigger** node
3. Configure:

**Cron Expression for Every 2 Weeks:**
```
0 2 * * 1,15
```

This runs:
- At 2:00 AM
- On the 1st and 15th of every month
- Every 2 weeks

**Alternative: Specific Days of the Week:**
```
0 2 * * 0
```

This runs:
- Every Sunday at 2:00 AM (weekly)

### Option B: Use n8n Manual Trigger + Cron (Alternative)

If you prefer Railway cron:

Create `railway.toml`:

```toml
[build]
builder = "DOCKERFILE"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 10000

[service]
cron = "0 2 * * 1,15"
```

This runs the health check endpoint every 2 weeks, which could trigger scraping.

**Recommended:** Use n8n schedule trigger (Option A) for more control.

---

## 📊 Step 4: Monitor Progress

### 4.1 Railway Logs (Real-Time)

1. Go to Railway project
2. Click scraper service
3. **Logs** tab shows:
   - Batch progress
   - Success/failure counts
   - URLs being scraped

### 4.2 Supabase Dashboard (After Completion)

Check scraped URLs:

```sql
-- View recently completed URLs
SELECT 
  url,
  title,
  status,
  updated_at
FROM url_queue
WHERE status = 'completed'
ORDER BY updated_at DESC
LIMIT 50;
```

Check imported documents:

```sql
SELECT 
  metadata->>'title' as title,
  metadata->>'source' as url,
  metadata->>'scraped_at' as scraped_at
FROM documents
WHERE metadata->>'source_type' = 'web_scrape'
ORDER BY created_at DESC
LIMIT 20;
```

### 4.3 n8n Dashboard

After scraping completes, query your RAG chat system to verify content is searchable.

---

## 🔧 Troubleshooting

### Issue: "SUPABASE_KEY not configured"

**Solution:** Add environment variable in Railway:

1. Go to Railway project
2. **Settings** → **Variables**
3. Add:
   - Name: `SUPABASE_KEY`
   - Value: Your service role key

### Issue: No pending URLs found

**Solution:** Add URLs to queue first:

```sql
-- Insert URLs to queue
INSERT INTO url_queue (url, status) VALUES
  ('https://example.com/page1', 'pending'),
  ('https://example.com/page2', 'pending');
```

Or run sitemap import workflow first.

### Issue: Railway logs show browser crash

**Solution:** Reduce concurrency in `api_server.py`:

```python
# Line ~50
semaphore = asyncio.Semaphore(1)  # Was 2, reduce to 1
```

Redeploy:
```bash
railway up
```

### Issue: "Failed to generate embeddings"

**Cause:** Missing or invalid OpenAI API key

**Solution:**
1. Add `OPENAI_API_KEY` to Railway variables
2. Verify key has credits at https://platform.openai.com/usage

**Note:** Without embeddings, documents are still inserted but won't be searchable in RAG.

### Issue: URLs stuck in "processing" status

**Cause:** Railway service restarted during scraping

**Solution:** Reset in Supabase:

```sql
UPDATE url_queue SET status = 'pending' WHERE status = 'processing';
```

Then trigger bulk scrape again.

---

## 📈 Performance Tuning

### Railway Configuration

**Free Tier (512MB RAM):**
```python
semaphore = asyncio.Semaphore(1)  # 1 concurrent
batch_size = 2  # 2 URLs per batch
```
**Expected:** ~50-80 URLs/hour

**Paid Tier (1GB+ RAM):**
```python
semaphore = asyncio.Semaphore(2)  # 2 concurrent
batch_size = 5  # 5 URLs per batch
```
**Expected:** ~200-300 URLs/hour

### Edit in `api_server.py`:

```python
# Line ~50 (global variables)
semaphore = asyncio.Semaphore(2)  # Adjust concurrency

# Line ~460 (bulk scrape function)
batch_size = 5  # Adjust batch size
```

---

## 🔐 Security Notes

### Environment Variables

- ✅ **Railway Variables** - Secure (encrypted at rest)
- ❌ **Never commit** keys to Git
- ❌ **Never share** Railway dashboard URL publicly

### Service Role Key

Use Supabase **service role** key for bulk scraping:
- Has full write permissions
- Bypasses RLS policies
- Only use in trusted services (Railway, not web apps)

---

## 📅 Recommended Workflow

### Weekly Maintenance

1. **Check Railway logs** - Monitor scraping success rate
2. **Check failed URLs** - Reset and retry if needed:

```sql
-- View failed URLs
SELECT url, updated_at FROM url_queue WHERE status = 'failed' LIMIT 20;

-- Reset failed URLs
UPDATE url_queue SET status = 'pending' WHERE status = 'failed';
```

3. **Add new URLs** - Run sitemap import or manual insert
4. **Verify content** - Query RAG chat system to test

### Bi-Weekly Bulk Scrape

**Automated:**
- n8n schedule triggers at 2:00 AM
- Calls Railway `/scrape/bulk` endpoint
- Railway processes all pending URLs
- All content imported to RAG with embeddings

**Manual (if needed):**
1. Click **"Manual: Start URL Scraping"** in n8n
2. Watch Railway logs for progress
3. Verify in Supabase after completion

---

## 🆘 Emergency Recovery

### If Railway Service Crashes

1. **Check logs** - Identify error
2. **Reset stuck URLs:**
```sql
UPDATE url_queue SET status = 'pending' WHERE status = 'processing';
```
3. **Redeploy:**
```bash
railway up
```
4. **Trigger bulk scrape** from n8n

### If OpenAI Embeddings Fail

Documents are still inserted (without embeddings):

```sql
-- Find documents without embeddings
SELECT metadata->>'title', metadata->>'source'
FROM documents
WHERE metadata->>'no_embedding' = 'true'
LIMIT 20;
```

**Regenerate embeddings:**
```python
# Run locally
python regenerate_embeddings.py --batch-size 50
```

---

## 📚 Related Documentation

- **BULK_SCRAPE_GUIDE.md** - Local bulk scraping (not Railway)
- **Railway Deployment Guide.md** - General Railway setup
- **N8N Workflow Update Instructions.md** - n8n workflow details

---

## ✅ Checklist

- [ ] Deploy to Railway
- [ ] Configure environment variables (SUPABASE_KEY, OPENAI_API_KEY)
- [ ] Test `/scrape/bulk` endpoint
- [ ] Configure n8n schedule trigger (every 2 weeks)
- [ ] Test full cycle: n8n → Railway → Supabase
- [ ] Verify Railway logs show progress
- [ ] Check Supabase for scraped content
- [ ] Query RAG chat system to verify searchable
- [ ] Set up Railway log monitoring (optional)

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

---

## 📞 Support

### Check Status

```bash
# Railway health
curl https://your-url.up.railway.app/health
```

### View Logs

Railway Dashboard → Project → Service → Logs

### Reset URLs

```sql
-- Reset stuck processing URLs
UPDATE url_queue SET status = 'pending' WHERE status = 'processing';

-- Reset failed URLs
UPDATE url_queue SET status = 'pending' WHERE status = 'failed';
```

---

**Your automated bulk scraping system is ready!** 🚀

It will run automatically every 2 weeks, scrape all pending URLs from Railway, and import them to your RAG system - even when you're away.
