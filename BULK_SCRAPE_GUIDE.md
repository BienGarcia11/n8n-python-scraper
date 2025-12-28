# Bulk URL Scraper for RAG System

## 🎯 Purpose

**Problem:** Running the scraper continuously in n8n causes:
- n8n instance lagging
- Workflow hangs and crashes
- URLs not marked as completed properly
- Poor performance with large batches

**Solution:** `bulk_scrape_import.py` - A standalone script that:
- Scrapes all pending URLs directly from your database
- Imports content to Supabase with embeddings
- Bypasses n8n workflow completely
- More reliable and faster

---

## 📋 Prerequisites

### Required Environment Variables

Set these in your terminal or `.env` file:

```bash
# Windows CMD
set SUPABASE_KEY=your-supabase-anon-or-service-role-key
set OPENAI_API_KEY=your-openai-api-key

# Windows PowerShell
$env:SUPABASE_KEY="your-supabase-anon-or-service-role-key"
$env:OPENAI_API_KEY="your-openai-api-key"

# Linux/Mac
export SUPABASE_KEY='your-supabase-anon-or-service-role-key'
export OPENAI_API_KEY='your-openai-api-key'
```

### Get Your Credentials

**Supabase Key:**
1. Go to https://supabase.com/dashboard/project/ykohyrwipxpwztptfopi
2. Settings → API
3. Copy `anon public` key OR `service_role` key (for writes)
4. Use `service_role` key for full permissions

**OpenAI API Key:**
1. Go to https://platform.openai.com/api-keys
2. Create new key
3. Copy the key

---

## 🔧 Installation

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### Step 2: Verify Installation

```bash
python bulk_scrape_import.py --help
```

Should show usage options.

---

## 🚀 Usage

### Basic Usage - Process All Pending URLs

```bash
python bulk_scrape_import.py
```

This will:
1. Fetch all URLs with status `pending` from `url_queue` table
2. Scrape each URL using Playwright
3. Insert content to `documents` table with OpenAI embeddings
4. Update `url_queue` status to `completed`

### Limit Processing

```bash
python bulk_scrape_import.py --limit 100
```

Process only the first 100 pending URLs.

### Memory-Constrained Settings (Recommended for Railway)

```bash
python bulk_scrape_import.py --batch-size 3 --concurrency 2
```

- `--batch-size`: URLs per batch (default: 3)
- `--concurrency`: Concurrent pages (default: 2)

**Recommended for low-memory systems:**
```bash
python bulk_scrape_import.py --batch-size 2 --concurrency 1
```

### Fast Processing (High Memory)

```bash
python bulk_scrape_import.py --batch-size 10 --concurrency 5
```

**Recommended only for:**
- Local machines with 8GB+ RAM
- Railway paid tier (1GB+ RAM)
- AWS/GCP/Azure instances

---

## 📊 Output Example

```
🔌 Connecting to Supabase...
✓ Connected

📋 Fetching pending URLs...
✓ Found 45 pending URLs

⚙️  Configuration:
   Total URLs: 45
   Batch size: 3
   Total batches: 15
   Concurrency: 2
   OpenAI embeddings: Enabled

============================================================
BATCH 1: Processing 3 URLs
============================================================
    Scraping: https://example.com/page1 (attempt 1/3)
      ✓ Success: 125,430 → 8,921 chars
    Scraping: https://example.com/page2 (attempt 1/3)
      ✓ Success: 98,210 → 7,843 chars
    Scraping: https://example.com/page3 (attempt 1/3)
      ✓ Success: 142,890 → 10,234 chars
  ✓ Document inserted with embedding
  ✓ Document inserted with embedding
  ✓ Document inserted with embedding

📊 Batch 1/15 Summary:
   ✓ Success: 3
   ❌ Failed: 0
   Progress: 3/45 URLs processed

============================================================
BATCH 2: Processing 3 URLs
...

[Continues until all URLs processed]

============================================================
🎉 FINAL SUMMARY
============================================================
Total URLs processed: 45
✅ Successful: 42
❌ Failed: 3
Success rate: 93.3%

✅ Bulk import complete!
```

---

## 🔍 Troubleshooting

### Issue: "SUPABASE_KEY environment variable is required"

**Solution:** Set the environment variable:

```bash
# Windows
set SUPABASE_KEY=your-key

# PowerShell
$env:SUPABASE_KEY="your-key"

# Linux/Mac
export SUPABASE_KEY='your-key'
```

### Issue: Browser crashes or out of memory

**Solution:** Reduce concurrency and batch size:

```bash
python bulk_scrape_import.py --batch-size 2 --concurrency 1
```

### Issue: "Failed to generate embeddings"

**Cause:** Missing or invalid OpenAI API key

**Solution:**
1. Set `OPENAI_API_KEY` environment variable
2. Verify the key is valid at https://platform.openai.com/api-keys

**Note:** Without embeddings, documents are still inserted but won't be searchable in RAG.

### Issue: URLs stuck in "processing" status

**Cause:** Script crashed mid-execution

**Solution:** Reset stuck URLs in Supabase:

```sql
UPDATE url_queue SET status = 'pending' WHERE status = 'processing';
```

Then re-run the script.

---

## 📈 Performance Tips

### For Speed (High Memory Systems)

```bash
python bulk_scrape_import.py --batch-size 10 --concurrency 5 --limit 500
```

**Expected:** ~500 URLs/hour on 8GB+ RAM

### For Reliability (Low Memory / Railway)

```bash
python bulk_scrape_import.py --batch-size 3 --concurrency 2
```

**Expected:** ~100 URLs/hour on 512MB-1GB RAM

### For Testing

```bash
python bulk_scrape_import.py --limit 5
```

Process only 5 URLs to verify everything works.

---

## 🔄 Comparison: n8n vs Bulk Script

| Feature | n8n Workflow | Bulk Script |
|---------|---------------|--------------|
| **Performance** | Slow, lags n8n | Fast, standalone |
| **Reliability** | Crashes, hangs | Stable |
| **Resource Usage** | High (n8n + scraper) | Low (only scraper) |
| **Error Handling** | Workflow stops | Continues on error |
| **Memory** | 1GB+ | 150-200MB |
| **URL Tracking** | ❌ Unreliable | ✅ Accurate |
| **Batch Size** | 5 URLs (max) | Unlimited |
| **Scalability** | ❌ Poor | ✅ Excellent |

---

## 🎯 Recommended Workflow

### Option 1: Full Bulk Import (One-Time Setup)

1. Add URLs to `url_queue` table (via sitemap or manual)
2. Run bulk scraper:

```bash
python bulk_scrape_import.py
```

3. All URLs scraped and imported to RAG
4. Use n8n only for:
   - Daily/weekly sitemap updates
   - Individual URL additions
   - Chat queries

### Option 2: Scheduled Bulk Imports

**Windows Task Scheduler:**
```bash
schtasks /create /tn "Bulk Scraper" /tr "python bulk_scrape_import.py" /sc weekly /d SUN
```

**Linux Cron:**
```bash
0 2 * * 0 /path/to/bulk_scrape_import.py >> /var/log/bulk_scraper.log 2>&1
```

This runs every Sunday at 2 AM to scrape new URLs.

### Option 3: Manual Bulk Imports (As Needed)

Whenever you have 20+ new URLs:

```bash
python bulk_scrape_import.py --limit 50
```

Process 50 newest URLs.

---

## 📝 Database Schema

### url_queue Table

```sql
CREATE TABLE url_queue (
  id SERIAL PRIMARY KEY,
  url TEXT UNIQUE NOT NULL,
  status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
  content TEXT,
  title TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### documents Table (RAG Knowledge Base)

```sql
CREATE TABLE documents (
  id SERIAL PRIMARY KEY,
  content TEXT NOT NULL,
  embedding VECTOR(1536),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 🔐 Security Notes

### API Keys

- **Never commit** `SUPABASE_KEY` or `OPENAI_API_KEY` to Git
- Use environment variables
- Use `.env` file (add to `.gitignore`)

### Service Role Key (Supabase)

For bulk imports, use `service_role` key:
- Has full write permissions
- Bypasses RLS policies
- Only use in trusted scripts (not web apps)

---

## 📚 Additional Resources

### n8n Workflow (Keep for Chat)

Keep using n8n for:
- **RAG Chat System** - Query your knowledge base
- **Email Indexing** - Auto-import emails from Outlook
- **Drive Indexing** - Auto-import files from Google Drive
- **Sitemap Updates** - Add new URLs to queue

### Bulk Script (Use for Scraping)

Use `bulk_scrape_import.py` for:
- **Scraping** large batches of URLs (100+)
- **Processing** pending URLs stuck in queue
- **Recovering** from n8n crashes
- **Initial data import** - Scrape 500+ URLs at once

---

## 🆘 Support

### Check Stuck URLs

```sql
-- View all pending URLs
SELECT url, status, created_at FROM url_queue WHERE status = 'pending' ORDER BY id DESC LIMIT 50;

-- Reset stuck URLs
UPDATE url_queue SET status = 'pending' WHERE status = 'processing';

-- View failed URLs
SELECT url, status, created_at FROM url_queue WHERE status = 'failed' ORDER BY id DESC LIMIT 50;
```

### View Imported Documents

```sql
SELECT 
  metadata->>'title' as title,
  metadata->>'source' as url,
  metadata->>'source_type' as type,
  metadata->>'scraped_at' as scraped_at
FROM documents 
WHERE metadata->>'source_type' = 'web_scrape'
ORDER BY created_at DESC 
LIMIT 20;
```

---

## ✅ Summary

**Use `bulk_scrape_import.py` when:**
- n8n is lagging or crashing
- You have 20+ URLs to scrape
- URLs are not being marked as completed
- You need faster performance

**Use n8n workflow when:**
- Querying your RAG system (chat)
- Adding 1-5 URLs at a time
- Indexing emails or Drive files
- Running scheduled sitemap updates

---

**Happy Scraping! 🚀**
