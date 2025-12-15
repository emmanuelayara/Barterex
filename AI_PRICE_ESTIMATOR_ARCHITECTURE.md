# AI Price Estimator - Architecture & Visual Guide

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BARTEREX UPLOAD PAGE                     │
│  /upload                                                        │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Item Details Form                                       │   │
│  │ ├─ Name input                                           │   │
│  │ ├─ Description (textarea)                               │   │
│  │ ├─ Condition (select: new/like-new/good/fair/poor)     │   │
│  │ ├─ Category (select)                                    │   │
│  │ └─ Images (drag & drop, max 6)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ [NEW!] AI Price Estimator Section                       │   │
│  │ ┌────────────────────────────────────────────────────┐  │   │
│  │ │  🤖 AI Price Estimator                             │  │   │
│  │ │  Get an estimated market value for your item      │  │   │
│  │ │                                                    │  │   │
│  │ │  [🔍 Estimate My Item's Value]                    │  │   │
│  │ └────────────────────────────────────────────────────┘  │   │
│  │                                                          │   │
│  │ [Appears only when all form fields are complete]       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Results Display (when button clicked)                   │   │
│  │                                                          │   │
│  │ [Loading...] → [Results Appear]                         │   │
│  │                                                          │   │
│  │ Estimated Market Value: $150.00                         │   │
│  │ Range: $120.00 - $180.00                                │   │
│  │ Confidence: ✅ High (based on 12 listings)             │   │
│  │                                                          │   │
│  │ 💰 Your Estimated Credits: $135.00                      │   │
│  │    (After 10% platform fee)                             │   │
│  │                                                          │   │
│  │ 📈 Based on 12 market listings                          │   │
│  │ ⏰ Updated just now                                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ [Submit Item to Platform]                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
                    FRONTEND (Browser)
                    ─────────────────
                          ↓
                    Upload Form Fill
                    (Name, Description,
                     Condition, Category,
                     Image)
                          ↓
                    [User Clicks Button]
                    "Estimate My Item's
                     Value"
                          ↓
┌─────────────────────────────────────────────────────────┐
│ JavaScript in upload.html                               │
│ ├─ Validate form fields                                │
│ ├─ Prepare FormData with image + description           │
│ ├─ Get CSRF token                                      │
│ └─ Send POST /api/estimate-price                       │
└─────────────────────────────────────────────────────────┘
                          ↓
                    NETWORK REQUEST
                          ↓
┌─────────────────────────────────────────────────────────┐
│ BACKEND (Flask)                                         │
│ routes/items.py                                         │
│ @app.route('/api/estimate-price', methods=['POST'])    │
│                                                         │
│ 1. Validate inputs                                      │
│    ├─ Description length >= 10 chars                    │
│    ├─ File type is image                               │
│    └─ File size <= 10MB                                │
│                                                         │
│ 2. Create AIPriceEstimator instance                    │
│    └─ from services.ai_price_estimator                 │
│                                                         │
│ 3. Call estimate_price()                               │
│    │                                                    │
│    ├─────────────────────────────────────────────┐     │
│    │ Step 1: Analyze Image                       │     │
│    │ ┌─────────────────────────────────────┐     │     │
│    │ │ OpenAI Vision API                   │     │     │
│    │ │ (requires OPENAI_API_KEY in .env)  │     │     │
│    │ └─────────────────────────────────────┘     │     │
│    │                    ↓                          │     │
│    │ Returns: { item_type, brand,                │     │
│    │            condition, features, age }       │     │
│    ├─────────────────────────────────────────────┤     │
│    │ Step 2: Build Search Query                  │     │
│    │ Combine: description + AI findings          │     │
│    ├─────────────────────────────────────────────┤     │
│    │ Step 3: Search Market Prices                │     │
│    │ ┌─────────────────────────────────────┐     │     │
│    │ │ Google Custom Search API            │     │     │
│    │ │ (requires GOOGLE_API_KEY in .env)  │     │     │
│    │ └─────────────────────────────────────┘     │     │
│    │                    ↓                          │     │
│    │ Returns: [eBay, FB Marketplace,            │     │
│    │           Craigslist, Amazon results]      │     │
│    ├─────────────────────────────────────────────┤     │
│    │ Step 4: Extract Prices                      │     │
│    │ Parse results for price mentions            │     │
│    │ Returns: [120, 150, 180, 160, ...]         │     │
│    ├─────────────────────────────────────────────┤     │
│    │ Step 5: Adjust for Condition                │     │
│    │ Apply multiplier:                           │     │
│    │ ├─ new:      × 1.0                          │     │
│    │ ├─ like-new: × 0.85                         │     │
│    │ ├─ good:     × 0.65  ← most users           │     │
│    │ ├─ fair:     × 0.45                         │     │
│    │ └─ poor:     × 0.25                         │     │
│    ├─────────────────────────────────────────────┤     │
│    │ Step 6: Calculate Estimate                  │     │
│    │ Statistical analysis:                       │     │
│    │ ├─ Min:    $120                             │     │
│    │ ├─ Max:    $180                             │     │
│    │ ├─ Median: $150  ← used as estimate         │     │
│    │ ├─ Avg:    $155                             │     │
│    │ └─ Confidence: high/medium/low              │     │
│    ├─────────────────────────────────────────────┤     │
│    │ Step 7: Calculate Credit Value              │     │
│    │ Formula:                                    │     │
│    │ net_credits = estimate × (1 - 0.10)        │     │
│    │ Example: $150 × 0.90 = $135                │     │
│    └─────────────────────────────────────────────┘     │
│                                                         │
│ 4. Return JSON Response                                │
│    ├─ price_estimate (with range & confidence)         │
│    └─ credit_value (net after fee)                     │
└─────────────────────────────────────────────────────────┘
                          ↓
                    NETWORK RESPONSE
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Frontend JavaScript                                     │
│ ├─ Receive JSON response                               │
│ ├─ Call displayPriceEstimate()                         │
│ ├─ Update UI with:                                     │
│ │  ├─ Estimated price: $150.00                         │
│ │  ├─ Price range: $120-$180                           │
│ │  ├─ Confidence: ✅ High                              │
│ │  ├─ Credit value: $135.00                            │
│ │  └─ Data sources                                     │
│ └─ Show results with smooth animation                  │
└─────────────────────────────────────────────────────────┘
                          ↓
                    USER SEES RESULTS!
```

## Component Architecture

```
services/
└── ai_price_estimator.py
    ├── AIPriceEstimator (class)
    │   ├── __init__()
    │   │   ├─ Load OpenAI API key from .env
    │   │   ├─ Load Google API keys from .env
    │   │   └─ Initialize cache
    │   │
    │   ├── estimate_price() [PUBLIC]
    │   │   └─ Main entry point
    │   │       ├─ Call _analyze_image()
    │   │       ├─ Call _search_market_prices()
    │   │       ├─ Call _adjust_for_condition()
    │   │       └─ Return final estimate
    │   │
    │   ├── _analyze_image() [PRIVATE]
    │   │   ├─ Validate API key
    │   │   ├─ Encode image to base64
    │   │   ├─ Call OpenAI API
    │   │   └─ Parse and return results
    │   │
    │   ├── _build_search_query() [PRIVATE]
    │   │   └─ Create optimized search string
    │   │
    │   ├── _search_market_prices() [PRIVATE]
    │   │   ├─ Call Google Custom Search API
    │   │   ├─ Extract results
    │   │   └─ Parse prices from snippets
    │   │
    │   ├── _extract_prices_from_results() [PRIVATE]
    │   │   └─ Use regex to find prices
    │   │
    │   ├── _adjust_for_condition() [PRIVATE]
    │   │   └─ Apply condition multipliers
    │   │
    │   ├── _calculate_final_estimate() [PRIVATE]
    │   │   ├─ Remove outliers
    │   │   ├─ Calculate min/max/avg/median
    │   │   ├─ Determine confidence
    │   │   └─ Return structured estimate
    │   │
    │   └── get_credit_value_estimate() [PUBLIC]
    │       └─ Convert price to platform credits
    │
    └── get_price_estimator() [FUNCTION]
        └─ Get/create singleton instance
```

## File Modification Summary

### 1. Created: `services/ai_price_estimator.py` (430 lines)
```
NEW FILE
│
├─ Imports: requests, os, base64, json, logging, datetime
├─ Custom Exception: PriceEstimationError
├─ Main Class: AIPriceEstimator
│  ├─ 11 methods total
│  ├─ Handles API calls to OpenAI & Google
│  ├─ Statistical analysis
│  ├─ Fallback estimates
│  └─ Credit calculation
└─ Helper: get_price_estimator() singleton
```

### 2. Modified: `routes/items.py` (added ~80 lines)
```
CHANGES:
├─ Import: jsonify from flask
├─ Import: AIPriceEstimator service
└─ New Route: POST /api/estimate-price (60 lines)
   ├─ @login_required (secure)
   ├─ Accepts: description, condition, category, image
   ├─ Returns: JSON with estimate + credits
   └─ Error handling
```

### 3. Modified: `templates/upload.html` (added ~500 lines)
```
CHANGES:
├─ CSS Styles (~200 lines)
│  ├─ .ai-estimator-section
│  ├─ .estimate-btn
│  ├─ .estimator-result
│  ├─ .price-display
│  ├─ .credit-display
│  └─ Animations & responsive design
│
├─ HTML Markup (~100 lines)
│  ├─ Estimator container
│  ├─ Button
│  ├─ Loading state
│  └─ Results display
│
└─ JavaScript Functions (~200 lines)
   ├─ checkEstimatorAvailability()
   ├─ estimatePrice()
   ├─ displayPriceEstimate()
   └─ Event listeners
```

## User Interaction Flow

```
1. USER ARRIVES AT /upload
   └─ Sees empty form

2. USER FILLS FORM
   └─ JavaScript monitors each field

3. ALL FIELDS COMPLETE?
   ├─ Name: filled
   ├─ Description: >= 10 chars
   ├─ Condition: selected
   ├─ Category: selected
   └─ Image: uploaded
   
4. AI ESTIMATOR APPEARS ✨
   └─ With purple gradient styling

5. USER CLICKS BUTTON
   └─ "Estimate My Item's Value"

6. LOADING STATE SHOWS
   └─ 🤖 Analyzing your item with AI...

7. SYSTEM WORKS
   ├─ Analyzes image (OpenAI)
   ├─ Searches prices (Google)
   ├─ Calculates estimate
   └─ Converts to credits

8. RESULTS DISPLAY
   ├─ 💰 $150.00 estimated price
   ├─ 📊 High confidence
   ├─ 🎁 $135.00 credits
   └─ 📈 Data source info

9. USER MAKES INFORMED DECISION
   ├─ Understands item value
   ├─ Knows what credits they'll get
   └─ Submits with confidence!
```

## Configuration Locations

```
Environment Variables (.env)
├─ OPENAI_API_KEY                    (OpenAI account)
├─ GOOGLE_API_KEY                    (Google Cloud)
└─ GOOGLE_SEARCH_ENGINE_ID          (Custom Search setup)

Code Configuration (ai_price_estimator.py)
├─ Condition Multipliers
│  ├─ new: 1.0 (100%)
│  ├─ like-new: 0.85 (85%)
│  ├─ good: 0.65 (65%)
│  ├─ fair: 0.45 (45%)
│  └─ poor: 0.25 (25%)
│
├─ Category Fallbacks
│  ├─ electronics: $150
│  ├─ furniture: $200
│  ├─ clothing: $30
│  └─ ... (13 categories)
│
└─ Platform Commission: 0.10 (10%)
```

## Response Time Expectations

```
Component                          Time
─────────────────────────────────────────
Form submission                    50 ms
─────────────────────────────────────────
Image upload                       100-500 ms
─────────────────────────────────────────
OpenAI Vision API                  3-8 seconds
├─ Network latency                 500 ms
├─ Image processing                2 sec
└─ Response                        500-1500 ms
─────────────────────────────────────────
Google Search API                  1-3 seconds
├─ Query construction              50 ms
├─ Network latency                 500 ms
├─ Search processing               1-2 sec
└─ Results return                  200 ms
─────────────────────────────────────────
Price extraction & calc            200 ms
─────────────────────────────────────────
JSON serialization                 50 ms
─────────────────────────────────────────
Network response to browser        100 ms
─────────────────────────────────────────
Frontend render                    200 ms
─────────────────────────────────────────
TOTAL                              4-12 seconds
```

## Error Handling Paths

```
POST /api/estimate-price
└─ Invalid input?
   ├─ Description < 10 chars
   │  └─ Return 400: "Please provide detailed description"
   │
   ├─ No image
   │  └─ Continue (image is optional)
   │
   └─ File type not image
      └─ Skip image analysis

OpenAI API fails?
├─ No key configured
│  └─ Skip to market search only
│
├─ API error
│  └─ Log error, continue without image analysis
│
└─ Invalid response
   └─ Skip and use defaults

Google Search API fails?
├─ No key configured
│  └─ Use category fallback
│
├─ API error
│  └─ Log error, return fallback estimate
│
└─ No results found
   └─ Use category fallback

Final estimate always returns:
├─ Either: Real market data
├─ Or: Category-based fallback
└─ With confidence level indicator
```

## Confidence Level Logic

```
Confidence = based on data points and variability

HIGH (8+ data points found)
├─ Multiple sources found
├─ Prices converge closely
└─ Trust this estimate!

MEDIUM (4-7 data points found)
├─ Some market data available
├─ Some price variance
└─ General guideline provided

LOW (< 4 data points found)
├─ Limited market data
├─ Or using fallback category
└─ Rough estimate only
```

## Security Layers

```
Request Level:
├─ @login_required         (user must be logged in)
├─ CSRF token validation   (prevent cross-site requests)
└─ API key headers         (prevent direct API abuse)

Input Level:
├─ Description validation  (min 10 chars)
├─ File type checking      (images only)
└─ File size limits        (10 MB max)

Processing Level:
├─ Try/catch blocks        (handle API errors)
├─ Timeout protection      (prevent hanging)
└─ Logging                 (audit trail)

Output Level:
├─ Error messages safe     (no sensitive info)
├─ JSON serialization      (prevent injection)
└─ CORS headers           (if needed)
```

This architecture provides a robust, scalable, and user-friendly AI price estimation system! 🚀
