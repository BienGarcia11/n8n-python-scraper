# Quick Start: Bulk URL Scraper

## 🚀 Get Started in 3 Steps

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### Step 2: Set Environment Variables

**Option A: Create .env file**
```bash
copy .env.example .env
```

Edit `.env` with your actual keys:
```
SUPABASE_URL=https://ykohyrwipxpwztptfopi.supabase.co
SUPABASE_KEY=your-actual-service-role-key
OPENAI_API_KEY=sk-your-actual-openai-key
```

**Option B: Set in terminal (Windows)**
```bash
set SUPABASE_KEY=your-service-role-key
set OPENAI_API_KEY=sk-your-openai-key
```

### Step 3: Run the Scraper

```bash
python bulk_scrape_import.py
```

---

## 📊 What It Does

1. **Fetches** all pending URLs from your `url_queue` table
2. **Scrapes** each URL using Playwright (Chrome)
3. **Generates** embeddings with OpenAI
4. **Inserts** content to `documents` table
5. **Updates** URL status to `completed`

---

## 💡 Common Commands

### Test with 5 URLs
```bash
python bulk_scrape_import.py --limit 5
```

### Low Memory Settings (Railway)
```bash
python bulk_scrape_import.py --batch-size 2 --concurrency 1
```

### Fast Processing (Local Machine)
```bash
python bulk_scrape_import.py --batch-size 10 --concurrency 5
```

---

## 🔑 Where to Get Keys

### Supabase Service Role Key
1. Go to: https://supabase.com/dashboard/project/ykohyrwipxpwztptfopi/settings/api
2. Scroll down to **Project API keys**
3. Copy `service_role` key
4. Use this for full write permissions

### OpenAI API Key
1. Go to: https://platform.openai.com/api-keys
2. Click **Create new secret key**
3. Copy the key
4. Never share this publicly

---

## 🆘 Troubleshooting

### "SUPABASE_KEY environment variable is required"
- Set environment variables or create `.env` file

### "Failed to generate embeddings"
- Verify `OPENAI_API_KEY` is set correctly
- Check OpenAI account has credits

### Browser crashes / Out of memory
- Reduce concurrency: `--concurrency 1`
- Reduce batch size: `--batch-size 2`

---

## 📖 Full Documentation

See `BULK_SCRAPE_GUIDE.md` for complete documentation.

---

## ✅ Success Indicators

You should see output like:
```
✓ Found 45 pending URLs
✓ Document inserted with embedding
✓ Success: 42/45
```

Then query your n8n RAG chat system to verify content is searchable!
