# AI Price Estimator - Quick Reference

## ⚡ Quick Start (5 minutes)

### 1. Install Dependencies
```bash
pip install requests openai
```

### 2. Add to .env
```env
OPENAI_API_KEY=sk-...your-key...
GOOGLE_API_KEY=...your-key...
GOOGLE_SEARCH_ENGINE_ID=...your-cx...
```

### 3. Restart Flask
```bash
python app.py
```

### 4. Test on Upload Page
Go to `/upload` and fill in item details - the AI estimator button will appear!

---

## 📋 What Users See

When a user uploads an item, they now see:

1. **Upload Form** (existing) - Name, description, condition, category, images
2. **AI Estimator Section** (NEW!) - Appears after all fields are filled
3. **Price Results** (NEW!) - Shows:
   - 💰 Estimated market price
   - 📊 Price range (min-max)
   - ✅ Confidence level
   - 🎁 **How many credits they'll get** (after 10% fee)
   - 📈 Number of market listings analyzed

---

## 🔧 Files Created/Modified

| File | Purpose |
|------|---------|
| `services/ai_price_estimator.py` | ✨ NEW - Core estimation engine |
| `routes/items.py` | 📝 Modified - Added `/api/estimate-price` endpoint |
| `templates/upload.html` | 📝 Modified - Added estimator UI + JavaScript |
| `.env` | 📝 Modified - Add API keys |

---

## 🔌 API Keys Needed

### OpenAI (Image Analysis)
- Get at: https://platform.openai.com/api-keys
- Costs: ~$30/month subscription includes thousands of requests
- Used for: Analyzing product images

### Google Custom Search (Price Lookup)
- Get at: https://console.cloud.google.com/
- Custom Search Engine: https://cse.google.com/cse/
- Costs: Free for 100/day, then $5 per 1k after that
- Used for: Finding similar items online

---

## 💡 How It Works (User Perspective)

```
User fills form
    ↓
AI Estimator button appears
    ↓
User clicks "Estimate My Item's Value"
    ↓
System analyzes image + description
    ↓
System searches internet for similar items
    ↓
Shows estimated price + credits they'll get
    ↓
User can submit form with confidence about their item's value!
```

---

## 🎯 Key Features

✅ **Real-time** - Results appear within 5-30 seconds
✅ **Smart** - AI analyzes images for condition and details
✅ **Accurate** - Based on actual market listings
✅ **Transparent** - Shows confidence level and data sources
✅ **Helpful** - Shows exact credit value after platform fees
✅ **Reliable** - Works even if APIs are down (fallback estimates)

---

## ⚙️ Configuration

Want to adjust something?

**Change condition multipliers** (what % of price for different conditions):
- File: `services/ai_price_estimator.py`
- Function: `_adjust_for_condition()`
- Example: change `'good': 0.65` to `'good': 0.70`

**Change category fallback prices**:
- File: `services/ai_price_estimator.py`
- Function: `_get_fallback_estimate()`
- Change values in `category_averages` dict

**Change platform commission rate**:
- File: `services/ai_price_estimator.py`
- Function: `get_credit_value_estimate()`
- Change `platform_commission = 0.10` to desired rate

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Estimator button doesn't appear | Fill in ALL form fields completely |
| "Unable to estimate price" error | Check API keys in .env are correct |
| Returns low confidence estimates | Normal for niche items - still useful! |
| Estimates seem too high/low | Adjust condition multipliers in config |

---

## 📊 Pricing Examples

### Example 1: iPhone in Good Condition
- Market price found: $500-600
- Good condition multiplier: 0.65
- Adjusted estimate: **$360**
- Platform fee (10%): $36
- User gets: **$324 in credits** ✨

### Example 2: Desk Furniture (New)
- Market price found: $400
- New condition multiplier: 1.0
- Estimated value: **$400**
- Platform fee (10%): $40
- User gets: **$360 in credits** ✨

---

## 🚀 Next Steps

1. Get your API keys
2. Add them to .env
3. Restart Flask
4. Go to /upload and test it out!
5. Customize multipliers if needed

---

## 📞 Support

If things aren't working:

1. Check Flask console for errors
2. Verify API keys are in .env
3. Make sure keys are active in respective dashboards
4. Check that all Python packages are installed

Debug tip: Add this to see detailed logs:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Enjoy! 🎉
