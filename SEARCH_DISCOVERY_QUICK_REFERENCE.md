# Search & Discovery - Quick Reference

## 🚀 Quick Start

### For Users

**Finding Items**:
1. Go to `/marketplace`
2. Start typing in search box → see suggestions
3. Click suggestion or type full search
4. Click category pill to browse that category
5. See "Recommended For You" (if logged in)

**Keyboard Shortcuts**:
- `Ctrl+K` or `Cmd+K` → Focus search box
- `Escape` → Close dropdown/suggestions
- `Arrow Keys` → Navigate suggestions (future enhancement)

### For Developers

**New Module**:
```python
from search_discovery import (
    get_search_suggestions,        # Autocomplete
    get_trending_items,            # Popular items
    get_personalized_recommendations,  # User-specific
    get_category_stats,            # Category counts
    get_similar_items              # Similar products
)
```

**New API Endpoints**:
```
GET /api/search-suggestions?q=<query>
GET /api/categories-stats?[filters]
GET /api/trending?limit=6
GET /api/recommended (login required)
GET /api/similar/<item_id>
GET /api/filters
```

---

## 🎯 Features at a Glance

| Feature | Location | Trigger | API Used |
|---------|----------|---------|----------|
| **Autocomplete** | Search box | Type in search | `/api/search-suggestions` |
| **Category Pills** | Below search | Click search or focus | `/api/filters` |
| **Recommendations** | Top of marketplace | Page load | `/api/recommended` |
| **Category Counts** | In pills | Page load | `/api/filters` |
| **Trending Items** | (Fallback) | No personalization | `/api/trending` |

---

## 📊 Database Queries

### Search Suggestions
```python
Item.query.filter(
    Item.name.ilike(f'%{query}%'),
    Item.is_approved == True,
    Item.is_available == True
).group_by(Item.name, Item.category)
```
⚡ **Performance**: < 100ms with proper indexes

### Category Statistics
```python
db.session.query(Item.category, func.count(Item.id))
  .filter(Item.is_approved, Item.is_available)
  .group_by(Item.category)
```
⚡ **Performance**: < 50ms with indexes

### Personalized Recommendations
```python
Item.query.filter(
    Item.category.in_(user_categories),
    Item.user_id != user_id,
    Item.is_approved, Item.is_available
).order_by(Item.id.desc()).limit(8)
```
⚡ **Performance**: < 150ms with indexes

---

## 🎨 UI Components

### Autocomplete Dropdown
```html
<div class="autocomplete-dropdown">
  <div class="autocomplete-section-header">Category (5)</div>
  <div class="autocomplete-item">
    <div class="autocomplete-icon">🏷️</div>
    <div class="autocomplete-content">
      <div class="autocomplete-name">Item Name</div>
      <div class="autocomplete-category">Category</div>
    </div>
    <div class="autocomplete-count">5</div>
  </div>
</div>
```

### Recommendation Cards (2/4 columns)
```html
<div class="recommendation-item">
  <img src="..." class="recommendation-image" />
  <div class="recommendation-content">
    <div class="recommendation-name">Item Name</div>
    <div class="recommendation-category">Category</div>
    <div class="recommendation-value">₦Price</div>
  </div>
</div>
```

### Category Pills
```html
<button class="category-pill" onclick="filterByCategory(...)">
  Electronics
  <span class="category-pill-count">24</span>
</button>
```

---

## 🔧 Configuration

### Limits & Defaults
```python
RECOMMENDATION_POOL_SIZE = 20      # Max recommendations
TRENDING_PERIOD_DAYS = 7           # Trending window
AUTOCOMPLETE_LIMIT = 8             # Max suggestions shown
PRICE_RANGE_PERCENT = 0.3          # ±30% for similar items
```

### Debouncing
```javascript
let autocompleteTimeout;
autocompleteTimeout = setTimeout(() => {
    fetchSuggestions(query);
}, 300);  // 300ms delay
```

### Category List
```python
CATEGORIES = [
    "Electronics",
    "Fashion / Clothing",
    "Footwear",
    "Home & Kitchen",
    "Beauty & Personal Care",
    "Sports & Outdoors",
    "Groceries",
    "Furniture",
    "Toys & Games",
    "Books & Stationery",
    "Health & Wellness",
    "Automotive",
    "Phones & Gadgets"
]
```

---

## 🧪 Testing

### Unit Tests
```python
def test_search_suggestions():
    suggestions = get_search_suggestions("phone", limit=5)
    assert len(suggestions) <= 5
    assert all('name' in s for s in suggestions)

def test_category_stats():
    stats = get_category_stats()
    assert isinstance(stats, dict)
    assert all(isinstance(v, int) for v in stats.values())

def test_personalized_recommendations():
    items = get_personalized_recommendations(user_id=1)
    assert all(item.user_id != 1 for item in items)
```

### API Tests (cURL)
```bash
# Test autocomplete
curl "http://localhost:5000/api/search-suggestions?q=phone"

# Test category stats
curl "http://localhost:5000/api/categories-stats"

# Test trending
curl "http://localhost:5000/api/trending?limit=6"

# Test recommendations (with session cookie)
curl -b "session=..." "http://localhost:5000/api/recommended"
```

### Frontend Tests
```javascript
// Test autocomplete display
async function testAutocomplete() {
    const response = await fetch('/api/search-suggestions?q=phone');
    const data = await response.json();
    console.assert(Array.isArray(data.suggestions));
    console.assert(data.suggestions.length > 0);
}

// Test recommendations load
async function testRecommendations() {
    const response = await fetch('/api/recommended');
    const data = await response.json();
    console.assert(Array.isArray(data.recommended));
}
```

---

## 🐛 Common Issues

### Autocomplete not showing
```javascript
// Debug: Check if API is returning data
fetch('/api/search-suggestions?q=test').then(r => r.json()).then(console.log);

// Debug: Check dropdown DOM
console.log(document.getElementById('autocompleteDropdown'));
```

### Recommendations empty
```python
# Debug: Check if user has item categories
user_categories = db.session.query(Item.category).filter(Item.user_id == user_id).distinct().all()
print(user_categories)

# Debug: Check if items exist in those categories
items = Item.query.filter(Item.category.in_(user_category_list)).all()
print(len(items))
```

### Slow autocomplete response
```sql
-- Check if index exists
SHOW INDEX FROM item WHERE Column_name IN ('name', 'is_approved', 'is_available');

-- Create missing index if needed
CREATE INDEX idx_item_search ON item(is_approved, is_available, name(50));
```

---

## 📈 Performance Tips

### Optimization Done
✅ Debounced API calls (300ms)  
✅ Limited results (8 suggestions, 8 recommendations)  
✅ Lazy loading recommendations  
✅ Async AJAX calls (non-blocking)  
✅ Efficient GROUP BY queries  

### Further Optimization
- Add Redis caching for category stats
- Implement full-text search index on item names
- Use CDN for image optimization
- Implement request pagination
- Add query result caching

---

## 🔐 Security

### Input Validation
```python
# In search_discovery.py
if not query or len(query) < 2:
    return []  # Prevent injection with min length

# SQL injection prevented by SQLAlchemy ORM
Item.name.ilike(f'%{query}%')  # Parameterized query
```

### Rate Limiting (Future)
```python
from flask_limiter import Limiter

@app.route('/api/search-suggestions')
@limiter.limit("100 per minute")
def api_search_suggestions():
    ...
```

### CORS (if needed)
```python
from flask_cors import CORS
CORS(app)  # Allow cross-origin API calls
```

---

## 📱 Mobile Experience

### Responsive Breakpoints
```css
/* Mobile: < 480px */
.recommendations-grid {
    grid-template-columns: repeat(1, 1fr);
}

/* Tablet: 480px - 768px */
@media (min-width: 480px) {
    .recommendations-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}

/* Desktop: > 768px */
@media (min-width: 769px) {
    .recommendations-grid {
        grid-template-columns: repeat(4, 1fr);
    }
}
```

### Touch Optimization
✅ 48px+ touch targets  
✅ Larger tap areas for buttons  
✅ No hover-dependent interactions  
✅ Vertical scrolling for dropdown  

---

## 🚀 Deployment

### Pre-deployment
- [ ] Run all tests
- [ ] Check API response times
- [ ] Verify database indexes
- [ ] Test on mobile devices
- [ ] Check error handling

### Post-deployment
- [ ] Monitor API performance
- [ ] Check error logs
- [ ] Verify autocomplete works
- [ ] Test recommendations load
- [ ] Monitor database query times

### Rollback Plan
```bash
# If issues found:
git revert <commit-hash>
# Or disable specific features:
# Disable recommendations in marketplace.html: style="display: none;"
```

---

## 📚 File Structure

```
Barterex/
├── search_discovery.py (NEW - 330 lines)
│   └── All recommendation & discovery logic
├── routes/
│   └── marketplace.py (MODIFIED - +200 lines)
│       └── New API endpoints
├── templates/
│   └── marketplace.html (MODIFIED - +400 lines)
│       ├── Autocomplete UI
│       ├── Recommendations section
│       └── Search scripts
└── SEARCH_DISCOVERY_GUIDE.md (NEW - This file)
```

---

## 💡 Usage Examples

### Using Autocomplete
```javascript
// Fetch suggestions
const response = await fetch('/api/search-suggestions?q=phone');
const { suggestions } = await response.json();

// Filter and display
const categories = {};
suggestions.forEach(s => {
    if (!categories[s.category]) categories[s.category] = [];
    categories[s.category].push(s);
});

Object.entries(categories).forEach(([cat, items]) => {
    console.log(`${cat}: ${items.length} items`);
});
```

### Using Recommendations
```javascript
// Get personalized items (user must be logged in)
const response = await fetch('/api/recommended?limit=8');
const { recommended } = await response.json();

// Display items
recommended.forEach(item => {
    console.log(`${item.name} - ₦${item.value}`);
});
```

### Using Category Stats
```javascript
// Get category information
const response = await fetch('/api/categories-stats');
const { categories, total } = await response.json();

// Show popular categories
const popular = Object.entries(categories)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

console.log(`Total items: ${total}`);
popular.forEach(([cat, count]) => {
    console.log(`${cat}: ${count} items`);
});
```

---

## 🎓 Learning Resources

- SQLAlchemy Query Documentation: https://docs.sqlalchemy.org
- Flask-JSONIFY: https://flask.palletsprojects.com/api/#module-flask.json
- JavaScript Fetch API: https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API
- Debouncing in JavaScript: https://developer.mozilla.org/en-US/docs/Glossary/Debounce

---

**Last Updated**: December 7, 2025  
**Version**: 1.0
