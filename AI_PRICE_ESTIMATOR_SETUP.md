# AI Price Estimator Setup Guide

## Overview

The AI Price Estimator is a powerful feature that helps users understand the market value of their items before uploading them to the Barterex platform. It uses:

1. **OpenAI Vision API** - Analyzes item images to identify product details
2. **Google Custom Search API** - Searches the internet for similar items and their prices
3. **Smart Fallback System** - Provides estimates based on category averages when external APIs are unavailable

## Features

✅ **Real-time Price Estimation** - Get instant market value estimates while filling out the upload form
✅ **Image Analysis** - AI vision analyzes photos to identify condition, features, and specifications
✅ **Market Research** - Searches multiple marketplaces for price comparisons
✅ **Credit Value Calculation** - Shows exactly how many credits users will receive after platform fees
✅ **Confidence Metrics** - Displays confidence level based on available market data
✅ **Smart Fallbacks** - Works even when APIs are unavailable using category-based estimates

## Installation Steps

### 1. Install Required Python Packages

Add these to your requirements.txt:

```
requests==2.31.0
openai==1.3.0
python-dotenv==1.0.0
```

Then install:
```bash
pip install -r requirements.txt
```

### 2. Get API Keys

#### OpenAI API Key (for Vision Analysis)
- Go to https://platform.openai.com/api-keys
- Create a new API key
- Copy and save it securely

#### Google Custom Search API (for Price Searching)
- Go to https://console.cloud.google.com/
- Create a new project
- Enable the Custom Search API
- Create credentials (API key)
- Set up a Custom Search Engine at https://cse.google.com/cse/all
- You'll need:
  - `GOOGLE_API_KEY` - Your API key
  - `GOOGLE_SEARCH_ENGINE_ID` - Your custom search engine ID (cx parameter)

### 3. Add Environment Variables

Update your `.env` file with:

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Google Search Configuration
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_SEARCH_ENGINE_ID=your_custom_search_engine_id_here
```

**Important:** Keep these keys secure and never commit them to version control!

### 4. File Structure

The system consists of:

```
Barterex/
├── services/
│   ├── __init__.py
│   └── ai_price_estimator.py          # Main price estimation service
├── routes/
│   └── items.py                        # Contains /api/estimate-price endpoint
├── templates/
│   └── upload.html                     # Updated with AI estimator UI
└── .env                                # API keys (not in git)
```

## How It Works

### User Flow

1. **Fill Upload Form** - User provides:
   - Item name
   - Detailed description
   - Item condition (new, like-new, good, fair, poor)
   - Category
   - At least one image

2. **AI Estimator Appears** - Once all fields are complete, the estimator button becomes visible

3. **Click "Estimate My Item's Value"** - User initiates the estimation:
   - Sends primary image + description + condition + category to `/api/estimate-price`
   - AI analyzes the image
   - System searches for comparable items online
   - Prices are adjusted based on condition
   - Final estimate is calculated

4. **View Results** - User sees:
   - Estimated market price
   - Price range (min-max)
   - Confidence level
   - **Estimated credits** they'll receive after 10% platform fee
   - Number of market listings analyzed

### Technical Process

```
User Data (Image + Description)
    ↓
1. Image Analysis (OpenAI Vision API)
   └─ Identifies: item type, brand, condition, age
    ↓
2. Build Search Query
   └─ Combines description + AI findings
    ↓
3. Search Market Prices (Google Custom Search)
   └─ Finds similar items on eBay, Facebook Marketplace, etc.
    ↓
4. Extract Prices
   └─ Parses prices from search results
    ↓
5. Adjust for Condition
   └─ Applies multipliers based on item condition
    ↓
6. Calculate Estimate
   └─ Statistical analysis: min, max, median, average
    ↓
7. Calculate Credits Value
   └─ Subtracts 10% platform fee
    ↓
User sees: Price Range + Confidence + Credits Value
```

## API Endpoint

### POST `/api/estimate-price`

**Request:**
```json
{
  "description": "string (required, min 10 chars)",
  "condition": "string (new|like-new|good|fair|poor, default: good)",
  "category": "string (optional)",
  "image": "file (optional)"
}
```

**Response (Success):**
```json
{
  "success": true,
  "price_estimate": {
    "estimated_price": 150.00,
    "price_range": {
      "min": 120.00,
      "max": 200.00,
      "average": 155.00
    },
    "confidence": "high|medium|low",
    "data_points": 12,
    "currency": "USD",
    "timestamp": "2025-12-15T10:30:00",
    "sources": "Based on 12 market listings"
  },
  "credit_value": {
    "gross_value": 150.00,
    "platform_commission": 15.00,
    "commission_rate": "10%",
    "net_credit_value": 135.00,
    "explanation": "You'll receive approximately $135.00 in credits after 10% platform fee"
  }
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "Error message"
}
```

## Configuration & Customization

### Condition Price Multipliers

Adjust how condition affects price estimates in `ai_price_estimator.py`:

```python
condition_multipliers = {
    'new': 1.0,           # 100% of found price
    'like-new': 0.85,     # 85% of found price
    'good': 0.65,         # 65% of found price
    'fair': 0.45,         # 45% of found price
    'poor': 0.25          # 25% of found price
}
```

### Category Fallback Prices

Customize fallback estimates in `_get_fallback_estimate()`:

```python
category_averages = {
    'electronics': 150,
    'furniture': 200,
    'clothing': 30,
    # Add or modify categories
}
```

### Platform Commission Rate

Change the commission percentage in `get_credit_value_estimate()`:

```python
platform_commission = 0.10  # Currently 10%
```

## Cost Considerations

### OpenAI Vision API
- **Cost:** ~$0.01 per image analysis
- **Included in:** OpenAI paid tier ($20+ monthly)
- **Usage:** Called once per price estimation

### Google Custom Search API
- **Cost:** Free for 100 queries/day, then $5 per 1000 queries
- **Included in:** Google Cloud Platform free tier
- **Usage:** Called once per price estimation

### Estimated Monthly Cost
- 100 estimations/day = 3000/month
- OpenAI: ~$30/month (included in subscription)
- Google: ~$15/month (for queries over 100/day)
- **Total:** ~$30-45/month for typical usage

## Troubleshooting

### API Key Issues

**Error: "OpenAI API key not configured"**
- Check `.env` file has `OPENAI_API_KEY`
- Restart Flask application after updating .env
- Verify API key is valid at https://platform.openai.com/account/api-keys

**Error: "Google API not configured"**
- Verify `GOOGLE_API_KEY` in `.env`
- Verify `GOOGLE_SEARCH_ENGINE_ID` in `.env`
- Test at https://cse.google.com/cse/ that your custom search engine works

### Estimation Returns Low Confidence

**Causes:**
- Very niche items with few market listings
- Poor image quality or unclear description
- Unusual item condition not matching standard categories

**Solution:** System will still provide estimates, but notes low confidence in UI

### No Results Found

**Fallback Behavior:**
- System automatically uses category-based estimates
- UI shows "low confidence" and explains this is an estimate
- Still provides useful price guidance to users

## Testing

### Test the Estimation Endpoint

```bash
curl -X POST http://localhost:5000/api/estimate-price \
  -F "description=Apple iPhone 13 Pro, 256GB, good condition" \
  -F "condition=good" \
  -F "category=electronics" \
  -F "image=@/path/to/phone_image.jpg"
```

### Disable APIs (Testing Fallbacks)

Temporarily comment out API keys in `.env` to test fallback behavior:

```python
# OPENAI_API_KEY=xxx  # Commented out
# GOOGLE_API_KEY=xxx  # Commented out
```

## Security Notes

⚠️ **Never commit API keys to git!**
- Add `.env` to `.gitignore`
- Use environment variables for all sensitive data
- Rotate API keys regularly
- Monitor API usage in respective dashboards

✅ **Rate Limiting**
- Add rate limiting to `/api/estimate-price` endpoint
- Suggested: 5 requests per minute per user
- Prevents API abuse and cost overruns

✅ **Input Validation**
- Descriptions are validated (min 10 characters)
- File sizes are limited (10MB max)
- Allowed file types: image formats only

## Future Enhancements

🚀 **Planned Features:**
- Cache price estimates to reduce API calls
- Machine learning model for condition assessment
- Support for multiple images to calculate average condition
- Price trend analysis (show if item value is rising/falling)
- Integration with major marketplaces APIs (eBay, Amazon)
- Batch estimation for admin users
- Estimate history and price tracking

## Support & Debugging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check `app.log` or console output for detailed error messages.

## Questions?

For issues or questions about the AI Price Estimator:
1. Check logs in Flask console
2. Verify API keys are correct and active
3. Test APIs independently at their respective dashboards
4. Ensure all required packages are installed
