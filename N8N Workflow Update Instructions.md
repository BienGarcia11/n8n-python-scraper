# n8n Workflow Update Instructions

## Summary
The workflow has been updated to call Railway API instead of GitHub Actions. However, some manual updates are needed in the n8n UI.

## What Was Automatically Updated ✅

**"Trigger GitHub Scraper"** → **"Trigger Railway Scraper"**
- Changed to call Railway API: `https://your-railway-app.up.railway.app/scrape`
- Updated request body format to match Railway API
- URL is placeholder - replace with actual Railway URL after deployment

## Manual Updates Needed 🔧

### 1. Update Railway URL (CRITICAL)

After deploying to Railway:
1. Get your Railway URL from Railway dashboard
2. Open "Trigger Railway Scraper" node
3. Replace `https://your-railway-app.up.railway.app/scrape` with your actual URL
4. Save the node

### 2. Remove "Wait for Scraper Callback" Node

The Railway API returns results directly, so the webhook wait is not needed.

**Steps:**
1. Find node: "Wait for Scraper Callback" (webhook wait node)
2. Select and delete it
3. Delete the connection from "Trigger Railway Scraper" to "Wait for Scraper Callback"

### 3. Fix "Split Scraper Results" Node

The node has an invalid `include` parameter. Update it:

**Current Issue:**
- Invalid value for 'include' parameter

**Fix:**
1. Open "Split Scraper Results" node (Item Lists node)
2. Go to "Fields to Split Out" section
3. Change setting to:
   - **Mode**: "All Other Fields"
   - **Field to Split Out**: `body.results`
4. Save the node

### 4. Update Connection Flow

**Old Flow:**
```
Trigger GitHub Scraper → Wait for Scraper Callback → Split Scraper Results
```

**New Flow:**
```
Trigger Railway Scraper → Split Scraper Results
```

**Steps:**
1. Connect "Trigger Railway Scraper" output to "Split Scraper Results" input
2. Make sure the connection is on the **main** output (not error output)

### 5. Remove "Aggregate Batch URLs" Node (Optional)

The Railway API accepts a comma-separated string of URLs, so you can simplify the workflow:

**Option A: Keep Current Structure**
- Keep "Aggregate Batch URLs" node
- Use as-is

**Option B: Simplify (Recommended)**
1. Delete "Aggregate Batch URLs" node
2. Connect "Mark as Processing" directly to "Trigger Railway Scraper"
3. In "Trigger Railway Scraper", use:
   ```javascript
   ={ "urls": {{ $json.url }}, "callback_url": "..." }
   ```
   Note: This changes to single URL per request

**Recommendation**: Keep current structure for batch processing.

## Testing the Updated Workflow

### 1. Deploy to Railway First

1. Push code to GitHub
2. Deploy to Railway using "Railway Deployment Guide.md"
3. Get Railway URL
4. Update "Trigger Railway Scraper" node with actual URL

### 2. Test Workflow in n8n

1. Activate workflow
2. Manually trigger "Manual: Start URL Scraping"
3. Monitor Railway logs
4. Check n8n execution logs

### 3. Verify Results

Check that:
- Railway API receives the request
- Scraping completes successfully
- Results are returned to n8n
- URLs are marked as "completed" in database

## Railway URL Update Checklist

After Railway deployment, update this in n8n:

- [ ] Get Railway URL from dashboard
- [ ] Open "Trigger Railway Scraper" node
- [ ] Replace placeholder URL with actual Railway URL
- [ ] Save node
- [ ] Test with single URL
- [ ] Test with batch of URLs

## Troubleshooting

### Error: "Invalid value for 'include'"

**Solution**: Follow step 3 above to fix "Split Scraper Results" node

### Error: "No results returned"

**Check**:
- Railway URL is correct
- Railway service is running (check `/health`)
- Railway logs show requests

### Error: "Callback failed"

**Solution**: This error should not occur with Railway API (it returns results directly). Remove "Wait for Scraper Callback" node.

### Slow Response Times

**Cause**: Railway might be cold on first request
**Solution**: 
- Wait 40s after deployment before testing
- Consider Railway Hobby tier for always-warm instances

## Next Steps

1. ✅ Deploy code to GitHub
2. ✅ Deploy to Railway
3. ✅ Update Railway URL in n8n
4. ✅ Remove "Wait for Scraper Callback" node
5. ✅ Fix "Split Scraper Results" node
6. ✅ Test workflow
7. ✅ Monitor Railway logs
8. ✅ Remove GitHub Actions workflow (optional)
