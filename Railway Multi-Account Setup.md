# Railway Multi-Account Deployment Guide

## Problem
You logged into Railway with **GitHub Account B**, but your repository is in **GitHub Account A**.

## Solutions

### Option 1: Add Repository to Railway (Easiest) ✅

Railway allows you to deploy repositories from multiple GitHub accounts even if you're logged in with a different account.

**Steps:**
1. Go to your Railway project
2. Click "New Project" or "New Service"
3. Select **"Deploy from Git repo"**
4. Click **"Connect another repository"** or **"Add GitHub"**
5. Railway will redirect to GitHub login
6. **Log in with GitHub Account A** (the account that owns the repo)
7. Authorize Railway to access Account A's repositories
8. Now you can select repositories from Account A
9. Choose: `BienGarcia11/n8n-python-scraper`

**Result:** Railway will now have access to both GitHub accounts.

---

### Option 2: Invite Railway to Your Repo (Collaborator Approach)

If you want to keep using GitHub Account B on Railway:

1. Go to GitHub repository: `BienGarcia11/n8n-python-scraper`
2. Click **Settings** (repo settings)
3. Click **Collaborators & teams** → **People**
4. Click **"Add people"**
5. Invite the email associated with your Railway GitHub Account B
6. Set permission: **Maintain** or **Admin**
7. Click **"Invite"**
8. Accept the invitation on GitHub Account B
9. Go back to Railway
10. Now you should see the repository in the deploy list

---

### Option 3: Use Git URL (Manual Deploy)

If you can't connect GitHub accounts:

1. Go to Railway project
2. Click **"New Service"**
3. Select **"Git"** (not "GitHub")
4. Choose **"Custom Git URL"**
5. Enter: `https://github.com/BienGarcia11/n8n-python-scraper.git`
6. Railway will clone the repository directly
7. Build and deploy

**Note:** This won't auto-deploy on push. You'll need to trigger deployments manually.

---

### Option 4: Switch Railway Account (Cleanest)

If you prefer to use the same GitHub account everywhere:

1. Log out of Railway
2. Go to [railway.app](https://railway.app)
3. Log in with **GitHub Account A** (the repo owner)
4. Create new project
5. Deploy from `BienGarcia11/n8n-python-scraper`

**Note:** This means you'll have a fresh Railway account with Account A.

---

## Recommendation

**Use Option 1 (Add Repository)** because:
- ✅ Keeps both accounts accessible in Railway
- ✅ Can deploy from any connected account
- ✅ One-time setup
- ✅ Automatic deployments on push

## After Deployment

Once deployed, you'll get:
- **Railway URL**: `https://your-project.up.railway.app`
- **Logs**: Real-time logging
- **Health Check**: Automatic monitoring

## Troubleshooting

### Repository Not Showing After Connecting Account

**Possible causes:**
1. Repository is private
   - **Fix:** Make repo public OR ensure Railway has access to private repos
2. Repository hasn't synced yet
   - **Fix:** Wait 1-2 minutes after connecting account
3. Railway already has access but showing wrong account
   - **Fix:** Click "Change account" in deploy dialog

### Can't Invite Collaborator

**Possible causes:**
1. Repository belongs to organization
   - **Fix:** Ask organization admin to invite Railway user
2. No permission to add collaborators
   - **Fix:** Use Option 1 or 3 instead

### Git URL Deploy Fails

**Possible causes:**
1. Repository is private
   - **Fix:** Make repo public OR use GitHub token
2. Wrong Git URL format
   - **Fix:** Use `https://github.com/owner/repo.git` format
3. Branch doesn't exist
   - **Fix:** Specify branch: `https://github.com/owner/repo.git#main`

## Verification Steps

After deploying, verify:

1. **Check Railway Dashboard**
   - Service is running (green status)
   - URL is assigned
   - Logs show "🚀 Scraper API is ready (browser warm)"

2. **Test Health Endpoint**
   ```bash
   curl https://your-project.up.railway.app/health
   ```
   Expected response:
   ```json
   {
     "status": "healthy",
     "browser_warm": true
   }
   ```

3. **Test Scrape Endpoint**
   ```bash
   curl -X POST https://your-project.up.railway.app/scrape \
     -H "Content-Type: application/json" \
     -d '{
       "urls": ["https://example.com"]
     }'
   ```

## Next Steps After Deployment

1. Copy Railway URL from dashboard
2. Update "Trigger Railway Scraper" node in n8n
3. Test with single URL first
4. Test with batch of URLs
5. Monitor Railway logs for issues
