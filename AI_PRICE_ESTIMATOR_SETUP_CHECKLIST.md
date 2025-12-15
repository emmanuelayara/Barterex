# 📋 AI Price Estimator - Setup Checklist

Use this checklist to ensure everything is set up correctly.

---

## ✅ Pre-Setup Checklist

- [ ] Read `START_HERE_AI_PRICE_ESTIMATOR.md` (5 min read)
- [ ] Python 3.7+ installed (`python --version`)
- [ ] Flask application running without errors
- [ ] Database migrations up to date
- [ ] Git repository is clean (no uncommitted changes)

---

## ✅ Installation Checklist

### Step 1: Install Python Packages
```bash
pip install requests openai
```

- [ ] `requests` installed successfully
- [ ] `openai` installed successfully
- [ ] No dependency conflicts
- [ ] `pip list` shows both packages

### Step 2: Get API Keys

#### OpenAI
- [ ] Created account at https://platform.openai.com/
- [ ] Generated API key from https://platform.openai.com/api-keys
- [ ] Key is valid and active
- [ ] Key has credit balance (paid or free tier)
- [ ] Saved key securely

#### Google
- [ ] Created Google Cloud account
- [ ] Created new project in Google Cloud Console
- [ ] Enabled Custom Search API
- [ ] Created API key
- [ ] Created Custom Search Engine at https://cse.google.com/cse/
- [ ] Saved API key
- [ ] Saved CX (search engine ID)
- [ ] Tested search engine manually

### Step 3: Configure Environment
- [ ] `.env` file exists in project root
- [ ] Added `OPENAI_API_KEY=sk-...`
- [ ] Added `GOOGLE_API_KEY=...`
- [ ] Added `GOOGLE_SEARCH_ENGINE_ID=...`
- [ ] `.env` is in `.gitignore`
- [ ] No API keys in git history

### Step 4: Verify Code Changes
- [ ] `services/ai_price_estimator.py` exists
- [ ] `services/__init__.py` exists
- [ ] `routes/items.py` contains `/api/estimate-price` endpoint
- [ ] `templates/upload.html` contains estimator HTML/CSS/JS
- [ ] No syntax errors in Python files
- [ ] No syntax errors in JavaScript

### Step 5: Restart Flask
- [ ] Stopped Flask (Ctrl+C)
- [ ] Restarted with `python app.py`
- [ ] No startup errors in console
- [ ] Flask running on http://localhost:5000
- [ ] Can access application homepage

---

## ✅ Testing Checklist

### Manual UI Testing
- [ ] Go to http://localhost:5000/upload
- [ ] Can see the upload form
- [ ] Form has all fields: name, description, condition, category, images
- [ ] Can fill in item name
- [ ] Can fill in description (10+ characters)
- [ ] Can select condition from dropdown
- [ ] Can select category from dropdown
- [ ] Can upload image(s)

### Estimator Visibility
- [ ] After filling all fields, purple "AI Price Estimator" section appears
- [ ] Button says "Estimate My Item's Value"
- [ ] Button is clickable
- [ ] Can remove image and button disappears

### Estimator Functionality
- [ ] Click estimator button
- [ ] Loading spinner appears with message
- [ ] Wait 4-12 seconds
- [ ] Results section appears with:
  - [ ] Estimated market price
  - [ ] Price range (min-max)
  - [ ] Confidence level (high/medium/low)
  - [ ] Your estimated credits
  - [ ] Number of market listings
  - [ ] Data sources

### Fallback Testing (Optional - for when APIs down)
- [ ] Temporarily comment out API keys in `.env`
- [ ] Restart Flask
- [ ] Try estimation again
- [ ] Should still show estimate (with "low confidence")
- [ ] Message should indicate category-based estimate
- [ ] Uncomment API keys afterward

### Form Submission
- [ ] After estimation, can still submit form
- [ ] Item is saved to database
- [ ] Redirect to marketplace page
- [ ] Item appears as pending approval

---

## ✅ Browser Testing Checklist

### Console Checks
- [ ] Open browser Developer Tools (F12)
- [ ] Go to Console tab
- [ ] Fill form and click estimator
- [ ] No JavaScript errors
- [ ] No console warnings (except expected browser warnings)

### Network Checks
- [ ] Open Network tab in DevTools
- [ ] Click estimator button
- [ ] See POST request to `/api/estimate-price`
- [ ] Request returns HTTP 200
- [ ] Response contains JSON with price estimate
- [ ] See `OpenAI` API call in waterfall (if API key working)
- [ ] See `Google` API call in waterfall (if API key working)

### Responsive Design
- [ ] Test on desktop (1920x1080)
- [ ] Test on tablet (768px width)
- [ ] Test on mobile (375px width)
- [ ] UI looks good on all sizes
- [ ] No horizontal scrolling
- [ ] Text is readable
- [ ] Buttons are clickable

---

## ✅ API Key Validation Checklist

### OpenAI API Key
- [ ] Go to https://platform.openai.com/account/api-keys
- [ ] Verify your key is listed
- [ ] Verify it's not revoked/disabled
- [ ] Check account has active subscription or credits

### Google API Key
- [ ] Go to https://console.cloud.google.com/
- [ ] Select your project
- [ ] Check API & Services → Credentials
- [ ] Verify API key is listed
- [ ] Check API & Services → Enabled APIs
- [ ] Verify "Custom Search API" is enabled
- [ ] Go to https://cse.google.com/cse/
- [ ] Verify custom search engine exists
- [ ] Test search at your CSE control panel
- [ ] Verify CX (search engine ID) is correct

---

## ✅ Error Handling Checklist

### Test Error Cases
- [ ] Submit form without filling all fields
  - [ ] Estimator button should NOT appear
- [ ] Submit form without image
  - [ ] Estimator button should NOT appear
- [ ] Fill form with short description (<10 chars)
  - [ ] Estimator button should NOT appear
- [ ] Click estimator with invalid API key
  - [ ] Should show user-friendly error message
  - [ ] Should not crash
- [ ] Submit form while estimation is loading
  - [ ] Should disable submit button
  - [ ] Should not double-submit

### Check Logs
- [ ] Watch Flask console during estimation
- [ ] Should see log messages for each step
- [ ] No error tracebacks
- [ ] If APIs fail, should see fallback used

---

## ✅ Security Checklist

- [ ] API keys not visible in frontend code
- [ ] API keys only in `.env` file
- [ ] `.env` file in `.gitignore`
- [ ] No API keys in git history (`git log` search)
- [ ] CSRF token present in form
- [ ] User must be logged in to use estimator
- [ ] File uploads limited to images only
- [ ] File upload size limited (10MB)
- [ ] Input validation working (description length)

---

## ✅ Documentation Checklist

- [ ] Read `START_HERE_AI_PRICE_ESTIMATOR.md`
- [ ] Reviewed `AI_PRICE_ESTIMATOR_SETUP.md`
- [ ] Saved `AI_PRICE_ESTIMATOR_QUICK_REF.md` for future reference
- [ ] Team knows about other documentation files
- [ ] Documentation is accessible to team members
- [ ] Printed or bookmarked relevant docs

---

## ✅ Customization Checklist (Optional)

### Condition Multipliers
- [ ] Reviewed current multipliers in `services/ai_price_estimator.py`
- [ ] Decided if they need adjustment
- [ ] If changing, updated `_adjust_for_condition()` method
- [ ] Tested with different conditions after changes

### Platform Commission
- [ ] Reviewed current 10% fee in `get_credit_value_estimate()`
- [ ] Decided if it matches your business model
- [ ] If changing, updated the percentage
- [ ] Re-tested to verify credit calculations

### UI Colors
- [ ] Reviewed gradient colors in `templates/upload.html`
- [ ] Verified they match your brand
- [ ] If changing, updated CSS color values
- [ ] Tested on multiple browsers for consistency

### Category Fallback Prices
- [ ] Reviewed category averages in `_get_fallback_estimate()`
- [ ] Verified they make sense for your platform
- [ ] If changing, updated the prices
- [ ] Tested fallback by disabling API keys

---

## ✅ Performance Checklist

- [ ] Measured estimation time (should be 4-12 seconds)
- [ ] Checked that Flask doesn't hang during API calls
- [ ] Verified page doesn't block while estimating
- [ ] Tested with multiple concurrent estimations (if applicable)
- [ ] No memory leaks (watch memory usage over time)

---

## ✅ Deployment Readiness Checklist

- [ ] All code changes committed to git
- [ ] `.env` file NOT committed (only template)
- [ ] All dependencies in `requirements.txt`
- [ ] Documentation complete and clear
- [ ] Code reviewed for bugs
- [ ] No hardcoded values (all in config)
- [ ] Ready to deploy to staging

---

## ✅ Post-Deployment Checklist

- [ ] API keys configured on production server
- [ ] Flask restarted on production
- [ ] Tested on production URL
- [ ] Monitor API usage and costs
- [ ] Check logs for any errors
- [ ] Get user feedback
- [ ] Track estimation accuracy

---

## ✅ Monitoring & Maintenance

### Daily
- [ ] Check for errors in Flask logs
- [ ] Monitor API usage (cost tracking)
- [ ] Monitor response times

### Weekly
- [ ] Review estimation accuracy feedback
- [ ] Check API quotas haven't been exceeded
- [ ] Verify no API key issues

### Monthly
- [ ] Review API costs vs budget
- [ ] Analyze estimation patterns
- [ ] Plan optimizations if needed
- [ ] Update documentation if needed

---

## ✅ Troubleshooting Checklist

If something doesn't work:

- [ ] Check Flask console for errors
- [ ] Check browser console (F12) for JavaScript errors
- [ ] Verify `.env` has correct API keys
- [ ] Verify API keys are active in their dashboards
- [ ] Try restarting Flask
- [ ] Try clearing browser cache
- [ ] Check internet connection
- [ ] Check firewall/proxy isn't blocking APIs
- [ ] Read troubleshooting section in setup guide
- [ ] Check if APIs are experiencing outages

---

## ✅ Final Sign-Off

- [ ] All checklist items completed
- [ ] System tested and working
- [ ] Documentation reviewed
- [ ] Team trained (if applicable)
- [ ] Ready for production use
- [ ] Maintenance plan in place

---

## 🎉 You're All Set!

When all checkboxes are complete, your AI Price Estimator is ready to go!

**Start here:** `START_HERE_AI_PRICE_ESTIMATOR.md`

Good luck! 🚀
