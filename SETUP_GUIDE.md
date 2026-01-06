# Setup Guide for Web Scraper

This guide will help you configure and deploy the web scraper to Railway.

## Step 1: Get Your Supabase Credentials

### Supabase URL
Your Supabase project URL is:
```
https://ykohyrwipxpwztptfopi.supabase.co
```

### Supabase Service Key
You need to get the **service key** (not the anon key) from Supabase:

1. Go to https://supabase.com/dashboard/project/ykohyrwipxpwztptfopi/settings/api
2. Scroll down to "Project API keys"
3. Copy the `service_role` secret key
4. **Important**: This key has full access to your database, keep it secure!

## Step 2: Get Your OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Copy the key (starts with `sk-...`)
4. Make sure you have credits in your OpenAI account

## Step 3: Deploy to Railway

### Option A: Using Railway CLI (Recommended)

1. **Install Railway CLI** (if not already installed):
```bash
npm install -g @railway/cli
```

2. **Login to Railway**:
```bash
railway login
```

3. **Initialize Railway project**:
```bash
railway init
```
Select or create a new project.

4. **Link the service**:
```bash
railway up
```

5. **Set environment variables**:
```bash
railway variables set SUPABASE_URL=https://ykohyrwipxpwztptfopi.supabase.co
railway variables set SUPABASE_SERVICE_KEY=your-service-role-key-here
railway variables set OPENAI_API_KEY=your-openai-api-key-here
railway variables set MAX_URLS_PER_RUN=100
```

Replace the placeholder values with your actual keys.

6. **Deploy**:
```bash
railway up
```

7. **Monitor deployment**:
```bash
railway logs
```

### Option B: Using Railway Dashboard

1. Go to https://railway.app/new
2. Click "Deploy from GitHub repo"
3. Select `BienGarcia11/n8n-python-scraper`
4. Add environment variables in the "Variables" tab:
   - `SUPABASE_URL`: `https://ykohyrwipxpwztptfopi.supabase.co`
   - `SUPABASE_SERVICE_KEY`: Your service role key
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `MAX_URLS_PER_RUN`: `100`
5. Click "Deploy"

## Step 4: Verify Deployment

### Check Railway Logs
```bash
railway logs
```

You should see:
```
2025-01-06 - __main__ - INFO - Browser launched successfully
2025-01-06 - __main__ - INFO - Starting web scraper...
2025-01-06 - __main__ - INFO - Fetched X pending URLs
```

### Check Supabase Documents Table

After the scraper runs, check your `documents` table in Supabase:
```sql
SELECT COUNT(*) FROM documents;
```

You should see new documents with embeddings.

## Step 5: Configure Your RAG System

Now that you have documents with embeddings, you can query them:

### Example Query in n8n

1. Use the Supabase node in n8n
2. Execute a vector similarity search:
```sql
SELECT 
  id,
  content,
  metadata->>'title' as title,
  metadata->>'url' as url,
  1 - (embedding <=> '[your_query_embedding]') as similarity
FROM documents
ORDER BY embedding <=> '[your_query_embedding]'
LIMIT 5;
```

3. Pass the results to your AI/LLM node for context

## Step 6: Monitor and Scale

### Railway Monitoring
- View logs: `railway logs`
- View metrics: Railway dashboard
- Set up alerts in Railway

### Scaling Options
Edit `scraper.py` to adjust:
- `max_concurrent_scrapes`: Increase for faster processing (more resources)
- `MAX_URLS_PER_RUN`: Control batch size
- `page_timeout`: Adjust for slow websites

### Cost Optimization
- Reduce `MAX_URLS_PER_RUN` for smaller batches
- Reduce `max_concurrent_scrapes` to save memory
- Use smaller Railway instance types

## Troubleshooting

### Scraper not starting
1. Check Railway logs: `railway logs`
2. Verify all environment variables are set
3. Check if Railway has enough resources allocated

### No URLs processed
1. Verify `url_queue` table has pending URLs
2. Check Supabase connection status in logs
3. Verify service key permissions

### OpenAI API errors
1. Verify API key is valid
2. Check OpenAI billing status
3. Check rate limits

### Memory issues
1. Reduce `max_concurrent_scrapes` in `scraper.py`
2. Reduce `MAX_URLS_PER_RUN`
3. Upgrade Railway plan for more memory

## Next Steps

1. **Add more URLs to queue**:
```sql
INSERT INTO url_queue (url, status)
VALUES 
  ('https://example.com', 'pending');
```

2. **Test with your RAG system** in n8n

3. **Monitor performance** and optimize as needed

4. **Set up scheduling** (Railway supports cron jobs)

## Support

For issues:
1. Check logs: `railway logs`
2. Review this guide
3. Check main README.md
4. Open an issue on GitHub

## Important Notes

⚠️ **Security**:
- Never commit `.env` file to GitHub
- Rotate API keys if compromised
- Use service role key only in trusted environments

⚠️ **Cost**:
- OpenAI charges for embedding generation
- Railway charges for compute resources
- Monitor usage to control costs

⚠️ **Performance**:
- Start with conservative settings
- Monitor and scale up gradually
- Consider rate limiting for production

🎉 **You're ready to go!** Your scraper will automatically process URLs from your queue and populate your documents table with embeddings for your RAG system.
