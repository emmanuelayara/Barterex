# Google Custom Search API Setup Guide

## What You'll Get:
- Real market price searches from eBay, Amazon, Facebook Marketplace, etc.
- More accurate price estimates
- Confidence levels increase with market data

## Prerequisites:
- Google Account (create one if you don't have)
- Access to Google Cloud Console
- Your Barterex application files

---

## Step 1: Create a Google Cloud Project

### 1.1 Go to Google Cloud Console
- Visit: https://console.cloud.google.com/
- Sign in with your Google Account
- Click on the project dropdown at the top
- Click "NEW PROJECT"

### 1.2 Create New Project
- **Project name:** `Barterex` (or any name you prefer)
- **Organization:** Leave as is (or select your organization if you have one)
- Click "CREATE"
- Wait 1-2 minutes for the project to be created

### 1.3 Select Your Project
- Once created, click on the project name dropdown
- Select the `Barterex` project to activate it

---

## Step 2: Enable the Custom Search API

### 2.1 Enable API
- In the left sidebar, click "APIs & Services"
- Click "Enabled APIs & services"
- At the top, click "+ ENABLE APIS AND SERVICES"

### 2.2 Search for Custom Search API
- In the search box, type: `Custom Search API`
- Click on "Custom Search API" from the results
- Click the blue "ENABLE" button
- Wait for it to enable (should show "API enabled")

---

## Step 3: Create API Credentials

### 3.1 Create API Key
- In the left sidebar, go to "Credentials"
- Click "+ CREATE CREDENTIALS"
- Select "API Key" from the dropdown

### 3.2 Copy Your API Key
- A popup will appear with your API Key
- **Copy this key** and save it somewhere safe (you'll need it)
- Example format: `AIzaSyD-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
- Click "Close"

### 3.3 Restrict Your API Key (Optional but Recommended)
- Find your API key in the credentials list
- Click on it to edit
- Under "Application restrictions":
  - Select "HTTP referrers (web sites)"
  - Add your domain: `localhost` (for testing) and your production domain
- Under "API restrictions":
  - Select "Custom Search API"
  - Click "Save"

---

## Step 4: Set Up Custom Search Engine

### 4.1 Create Custom Search Engine
- Visit: https://programmablesearchengine.google.com/
- Click "Create" or "New search engine"
- Fill in the form:
  - **Search engine name:** `Barterex Item Pricing`
  - **What to search:** Select "Search the entire web"
  - Leave other options as default
- Click "Create"

### 4.2 Get Your Search Engine ID (CX)
- After creation, you'll see your search engine dashboard
- Look for "Search engine ID" (also called `cx`)
- **Copy this ID** and save it
- Example format: `a1234567890:abcdefghijk`

### 4.3 (Optional) Add Preferred Sites
If you want to prioritize certain marketplaces:
- In your search engine settings, click "Sites to search"
- Add preferred sites like:
  - `ebay.com`
  - `amazon.com`
  - `facebook.com/marketplace`
- This helps get more relevant price results

---

## Step 5: Add Credentials to Your Application

### 5.1 Update Your .env File
- Open `.env` file in your Barterex directory
- Add these lines (or update if they exist):

```env
# Google Custom Search API
GOOGLE_API_KEY=AIzaSyD-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GOOGLE_SEARCH_ENGINE_ID=a1234567890:abcdefghijk
```

Replace with your actual:
- `GOOGLE_API_KEY` = Your API Key from Step 3.2
- `GOOGLE_SEARCH_ENGINE_ID` = Your Search Engine ID (CX) from Step 4.2

### 5.2 Verify File Location
Make sure `.env` is in your project root:
```
c:\Users\ayara\Documents\Python\Barterex\.env
```

### 5.3 Save the File
- Save the `.env` file
- **Important:** Do NOT commit this to GitHub (should be in .gitignore)

---

## Step 6: Test Your Setup

### 6.1 Restart Your Application
- Stop your Flask server (if running)
- Start it again to load the new .env variables

### 6.2 Test Price Estimation
- Go to: `http://localhost:5000/valuate`
- Fill in item details:
  - Item Name: "iPhone 13"
  - Description: "Apple iPhone 13, 128GB, black, good condition"
  - Condition: "Good / Lightly Used"
  - Category: "Phones & Gadgets"
  - Images: (optional, up to 6)
- Click "Get Price Estimate"

### 6.3 Check the Logs
- Look at your terminal/console logs
- You should now see:
  ```
  Google API configured, searching market prices
  Found X price references for: iPhone 13 price...
  ```
  (Instead of "Google API not configured, using fallback prices")

### 6.4 Verify Results
- The result should show prices from real market listings
- Confidence level should be higher (Medium or High)
- Price range should reflect actual market data

---

## Troubleshooting

### Problem 1: "Google API not configured" Still Appears
**Solution:**
- Check that `.env` file has correct keys
- Verify key names are exactly: `GOOGLE_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID`
- Restart your Flask application
- Check that the API is enabled in Google Cloud Console

### Problem 2: "Invalid API Key" Error
**Solution:**
- Verify you copied the API key correctly
- Make sure there are no extra spaces or characters
- Check that the API key hasn't been revoked in Google Cloud Console

### Problem 3: "Search Engine ID is invalid"
**Solution:**
- Verify the Search Engine ID (CX) is correct
- Check you got it from the right search engine
- Make sure it's formatted correctly: `xxxx:xxxxxx`

### Problem 4: No Price Results Found
**Solution:**
- This is normal if the search query is too specific
- Try with more common item names
- The system will fall back to category estimates (which still work!)

### Problem 5: API Quota Exceeded
**Solution:**
- Google Custom Search has a free quota of 100 queries per day
- If you exceed this, you'll be charged or it will stop working
- Upgrade your plan in Google Cloud Console if needed
- See pricing below

---

## Pricing

### Free Tier (What You Get):
- **100 searches per day** (free)
- Perfect for testing and small applications

### Paid Tier (If You Need More):
- Beyond 100 searches: $5 per 1,000 queries
- Can be enabled in Google Cloud Console Billing

### How to Enable Paid:
- Go to Google Cloud Console
- Click on your project
- Go to "Billing"
- Click "Link Billing Account"
- Follow the steps to add a payment method

---

## Complete Verification Checklist

- [ ] Google Cloud Project created
- [ ] Custom Search API enabled
- [ ] API Key generated and copied
- [ ] Custom Search Engine created
- [ ] Search Engine ID (CX) copied
- [ ] `.env` file updated with `GOOGLE_API_KEY`
- [ ] `.env` file updated with `GOOGLE_SEARCH_ENGINE_ID`
- [ ] Flask app restarted
- [ ] Test valuation performed
- [ ] Results show real market prices (not fallback)
- [ ] Confidence level shows as Medium or High
- [ ] No errors in logs

---

## What Happens After Setup

### Before (Using Fallback):
```
Input: Samsung A23
Process: Category average lookup
Result: ₦180,000 (Low confidence)
```

### After (Using Google API):
```
Input: Samsung A23
Process: Searches eBay, Amazon, etc. for listings
Result: ₦250,000 - ₦380,000 (High confidence)
```

---

## Security Notes

⚠️ **Important:**
- Never commit `.env` to GitHub
- Check that `.env` is in `.gitignore`
- Keep your API keys secret
- Restrict API keys to your domains
- Monitor your API usage to avoid unexpected charges

---

## Next Steps After Setup

Once verified working:
1. You can increase the search scope (add more sites)
2. Customize the search engine for your market
3. Monitor API usage and costs
4. Consider setting up alerts for quota warnings

---

## Still Have Questions?

If something doesn't work:
1. Check the logs: `python app.py` and look for errors
2. Verify `.env` file exists and has correct keys
3. Test with a common item name (e.g., "iPhone")
4. Check Google Cloud Console that API is enabled

Your valuation system will now get real market prices! 🚀
