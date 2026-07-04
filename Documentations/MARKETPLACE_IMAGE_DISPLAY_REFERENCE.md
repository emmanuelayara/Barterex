# Marketplace Image Display - Complete Reference Guide

This document shows exactly how the marketplace successfully displays item images. Use this as a reference to replicate the pattern in the admin dashboard.

---

## 1. ROUTE HANDLER: How Items Are Retrieved

**File:** [routes/marketplace.py](routes/marketplace.py#L29-L95)

### Marketplace Route (Grid View)
```python
@marketplace_bp.route('/')
@marketplace_bp.route('/marketplace')
@handle_errors
def marketplace() -> Union[str, Response]:
    try:
        # Get filters from request
        page = request.args.get('page', 1, type=int)
        condition_filter = request.args.get('condition')
        category_filter = request.args.get('category')
        search = request.args.get('search', '')
        state = request.args.get('state', '')
        price_range = request.args.get('price_range')

        # Build filter conditions
        filters = [Item.is_approved == True, Item.is_available == True]
        
        if condition_filter:
            filters.append(Item.condition == condition_filter)
        if category_filter:
            filters.append(Item.category == category_filter)
        if search:
            filters.append(Item.name.ilike(f'%{search}%'))
        if state:
            filters.append(Item.location == state)
        # ... price range filtering ...
        
        filters.append(Item.value.isnot(None))

        # ✅ KEY: Use joinedload to eager-load Item.images
        items = Item.query.filter(and_(*filters))
                          .options(joinedload(Item.images))  # IMPORTANT!
                          .order_by(Item.id.desc())
                          .all()
        
        # Build breadcrumbs
        breadcrumbs = ['Marketplace']
        if category_filter:
            breadcrumbs.append(category_filter)
        if search:
            breadcrumbs.append(f'Search: {search}')
        
        # Pass items and breadcrumbs to template
        return render_template('marketplace.html', items=items, breadcrumbs=breadcrumbs)
        
    except Exception as e:
        logger.error(f"Marketplace search error: {str(e)}", exc_info=True)
        flash('An error occurred while searching the marketplace. Please try again.', 'danger')
        return redirect(url_for('marketplace.marketplace'))
```

### **Key Points:**
- ✅ Uses `joinedload(Item.images)` to eager-load related images (prevents N+1 queries)
- ✅ Filters for `is_approved=True` and `is_available=True`
- ✅ Passes `items` list to template with all images already loaded

---

### Item Detail Route (Single Item)
```python
@marketplace_bp.route('/item/<int:item_id>', methods=['GET', 'POST'])
@handle_errors
def view_item(item_id: int) -> Union[str, Response]:
    try:
        item = Item.query.get_or_404(item_id)
        
        # ✅ Query ItemImage records separately, ordered by position
        item_images = ItemImage.query.filter_by(item_id=item.id)\
                                     .order_by(ItemImage.order_index)\
                                     .all()
        
        # If no ItemImage records but has image_url, create TempImage
        if not item_images and item.image_url:
            class TempImage:
                def __init__(self, url, is_primary=True):
                    self.image_url = url
                    self.is_primary = is_primary
            
            item_images = [TempImage(item.image_url)]

        # Get related items (items in same category)
        related_items = Item.query.options(joinedload(Item.user), 
                                          joinedload(Item.images))\
                                   .filter(
            Item.category == item.category,
            Item.id != item.id,
            Item.is_available == True
        ).limit(5).all()

        logger.info(f"Item viewed - Item ID: {item_id}, Name: {item.name}")
        breadcrumbs = ['Marketplace', item.category, item.name[:50]]
        
        # ✅ Pass item_images list to template
        return render_template('item_detail.html', 
                             item=item, 
                             item_images=item_images,  # List of ItemImage objects
                             related_items=related_items, 
                             csrf_token=generate_csrf, 
                             breadcrumbs=breadcrumbs)
        
    except Exception as e:
        logger.error(f"Error viewing item {item_id}: {str(e)}", exc_info=True)
        flash(f'Could not load item. It may have been removed.', 'danger')
        return redirect(url_for('marketplace.marketplace'))
```

### **Key Points:**
- ✅ Retrieves ItemImage records directly using `ItemImage.query.filter_by(item_id=...)`
- ✅ Orders images by `order_index` to preserve upload order
- ✅ Falls back to `item.image_url` if no ItemImage records exist
- ✅ Passes `item_images` list to template for slideshow

---

## 2. TEMPLATE: How Images Are Displayed

### A. Marketplace Grid View

**File:** [templates/marketplace.html](templates/marketplace.html#L1670-L1720)

```html
{% for item in items %}
  <!-- Build image array using namespace to support list mutation -->
  {% set ns = namespace(images=[]) %}
  
  <!-- Add main image URL if it exists -->
  {% if item.image_url %}
    {% set _ = ns.images.append(item.image_url) %}
  {% endif %}
  
  <!-- Add all ItemImage records -->
  {% if item.images %}
    {% for img in item.images %}
      {% if img.image_url %}
        {% set _ = ns.images.append(img.image_url) %}
      {% endif %}
    {% endfor %}
  {% endif %}
  
  <!-- Create card with JSON array of images for carousel -->
  <div class="marketplace-item" 
       data-item-url="{{ url_for('marketplace.view_item', item_id=item.id) }}" 
       data-images='{{ ns.images | tojson }}'>
    
    <!-- Image Container -->
    <div class="item-image-container">
      {% if ns.images %}
        <!-- First image with lazy loading -->
        <img class="item-carousel-img" 
             src="{{ ns.images[0] | image_url }}" 
             alt="{{ item.name }}" 
             loading="lazy" 
             onerror="this.src='/static/placeholder.png'" />
      {% else %}
        <!-- Fallback placeholder -->
        <div style="height: 100%; background: linear-gradient(135deg, var(--primary-light) 0%, var(--primary-medium) 100%); display: flex; align-items: center; justify-content: center; color: var(--primary-color); font-size: 2rem;">📷</div>
      {% endif %}
      
      <!-- Image counter badge -->
      {% if ns.images|length > 1 %}
        <div class="image-counter">{{ ns.images|length }} images</div>
      {% endif %}
      
      <!-- Condition badge -->
      <div class="item-badge">{{ item.condition }}</div>
    </div>
    
    <!-- Other item info (name, price, location) -->
    <div class="item-content">
      <h4 class="item-title">{{ item.name }}</h4>
      <div class="item-location">Available in <strong>{{ item.location }}</strong></div>
      <div class="item-value">₦{{ "{:,.2f}".format(item.value) }}</div>
      <div class="item-actions">
        <a href="{{ url_for('marketplace.view_item', item_id=item.id) }}" class="btn-primary">
          👁️ View Details
        </a>
      </div>
    </div>
  </div>
{% endfor %}
```

### **Key Template Patterns:**

| Pattern | Purpose |
|---------|---------|
| `{% set ns = namespace(images=[]) %}` | Create mutable array for building image list |
| `{% if item.image_url %}` | Check if item has primary image |
| `{% set _ = ns.images.append(...) %}` | Add to array (Jinja2 requires assignment) |
| `{% if item.images %}` | Check if item has ItemImage records |
| `{{ ns.images \| tojson }}` | Convert array to JSON for JavaScript |
| `{{ ns.images[0] \| image_url }}` | Apply image_url filter to first image |
| `data-images='{{ ns.images \| tojson }}'` | Store JSON array on DOM element |

---

### B. Item Detail Slideshow

**File:** [templates/item_detail.html](templates/item_detail.html#L723-L950)

```html
<div class="slideshow-section">
  <div class="slideshow-container">
    {% if item_images and item_images|length > 0 %}
      <div class="slideshow-wrapper">
        <div class="slideshow-track" id="slideshowTrack">
          
          <!-- Loop through each image -->
          {% for image in item_images %}
            <div class="slide">
              {% if image.image_url %}
                <!-- Image with click to fullscreen -->
                <img src="{{ image.image_url | image_url }}" 
                     alt="{{ item.name }} - Image {{ loop.index }}" 
                     onclick="openFullscreen('{{ image.image_url | image_url }}')" 
                     style="cursor: pointer;">
              {% else %}
                <div class="slide-placeholder">📦</div>
              {% endif %}
            </div>
          {% endfor %}
          
        </div>
      </div>

      <!-- Navigation arrows (shown if multiple images) -->
      {% if item_images|length > 1 %}
        <button class="slideshow-nav prev" onclick="previousSlide()">‹</button>
        <button class="slideshow-nav next" onclick="nextSlide()">›</button>
      {% endif %}

      <!-- Image counter -->
      <div class="image-counter">
        <span id="currentSlide">1</span> / {{ item_images|length }}
      </div>

      <!-- Thumbnails (shown if multiple images) -->
      {% if item_images|length > 1 %}
        <div class="thumbnail-nav">
          {% for image in item_images %}
            <div class="thumbnail {% if loop.first %}active{% endif %}" 
                 onclick="goToSlide({{ loop.index0 }})" 
                 title="Image {{ loop.index }}">
              {% if image.image_url %}
                <img src="{{ image.image_url | image_url }}" 
                     alt="Thumbnail {{ loop.index }}">
              {% else %}
                <div class="thumbnail-placeholder">📦</div>
              {% endif %}
            </div>
          {% endfor %}
        </div>
      {% endif %}

    {% else %}
      <div class="slide-placeholder">📦</div>
      <div class="image-counter">No Images</div>
    {% endif %}
  </div>
</div>
```

### **Key Features:**
- ✅ Iterates through `item_images` list passed from route
- ✅ Applies `| image_url` filter to each image
- ✅ Shows navigation arrows only if multiple images
- ✅ Shows thumbnails with active state
- ✅ Shows image counter (e.g., "3 / 5")
- ✅ Supports fullscreen view on click

---

### C. Related Items Grid

```html
{% if related_items and related_items|length > 0 %}
  <div class="related-grid" id="relatedCarousel">
    {% for related in related_items %}
      <div class="related-item">
        <a href="{{ url_for('marketplace.view_item', item_id=related.id) }}">
          {% if related.images and related.images|length > 0 %}
            <!-- Display first image from ItemImage relationship -->
            <img src="{{ related.images[0].image_url | image_url }}" 
                 alt="{{ related.name }}" 
                 class="related-image" 
                 loading="lazy">
          {% else %}
            <!-- Fallback placeholder -->
            <div class="related-image" style="display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #f5f5f5 0%, #e8e8e8 100%); font-size: 2.5rem;">📦</div>
          {% endif %}
          <div class="related-content">
            <h4 class="related-name">{{ related.name }}</h4>
            <div class="related-price">₦{{ "{:,.2f}".format(related.value) }}</div>
          </div>
        </a>
      </div>
    {% endfor %}
  </div>
{% else %}
  <div class="empty-related">
    <div class="empty-related-icon">🔍</div>
    <div class="empty-related-text">No related items found</div>
  </div>
{% endif %}
```

---

## 3. IMAGE URL FILTER: Data Transformation

**File:** [app.py](app.py#L114-L160)

```python
# ✅ Jinja filter to format image URLs (supports both local and Cloudinary)
@app.template_filter('image_url')
def format_image_url(url):
    """Convert image URLs to absolute paths - serves from local storage on localhost"""
    from flask import current_app
    import os
    
    if not url:
        return '/static/placeholder.png'
    
    url = str(url).strip()
    logger.debug(f"🔍 Processing image URL: {url}")
    
    # If URL is already a full Cloudinary URL, return as-is
    if 'res.cloudinary.com' in url:
        logger.debug(f"✅ Full Cloudinary URL detected: {url}")
        return url
    
    # If URL already looks like a full HTTP/HTTPS URL, return as-is
    if url.startswith('http://') or url.startswith('https://'):
        logger.debug(f"✅ Full HTTP URL detected: {url}")
        return url
    
    # If already a /static/ path, just normalize slashes
    if url.startswith('/static/'):
        return url.replace('//', '/')
    
    upload_dir = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
    
    # Extract filename from any path format
    # Could be "barterex/1/1/0_filename.jpg" or just "filename.jpg"
    filename = url.split('/')[-1] if '/' in url else url
    filename = filename.strip('/')
    
    logger.debug(f"📄 Extracted filename: {filename}")
    
    # Try exact match first
    file_path = os.path.join(upload_dir, filename)
    if os.path.exists(file_path):
        logger.debug(f"✅ File found at: {file_path}")
        return f'/static/uploads/{filename}'
    
    logger.debug(f"❌ File not found at: {file_path}")
    
    # Try removing the first underscore-separated component
    # (e.g., "0_1_0_..." -> "1_0_...")
    if '_' in filename:
        parts = filename.split('_', 1)
        if len(parts) > 1:
            alt_filename = parts[1]
            alt_path = os.path.join(upload_dir, alt_filename)
            if os.path.exists(alt_path):
                logger.debug(f"✅ File found with alt name: {alt_filename}")
                return f'/static/uploads/{alt_filename}'
            logger.debug(f"❌ Alt file not found: {alt_path}")
    
    # File not found, return placeholder
    logger.warning(f"⚠️ Image file not found: {filename}")
    return '/static/placeholder.png'
```

### **Filter Logic:**
1. ✅ Returns placeholder if URL is empty/None
2. ✅ Returns Cloudinary URLs unchanged (`res.cloudinary.com`)
3. ✅ Returns full HTTP/HTTPS URLs unchanged
4. ✅ Normalizes `/static/` paths
5. ✅ Extracts filename from complex paths
6. ✅ Checks if file exists on disk
7. ✅ Tries alternative filename variations
8. ✅ Falls back to placeholder if file not found

---

## 4. CAROUSEL JAVASCRIPT

**File:** [templates/marketplace.html](templates/marketplace.html#L2146-L2210)

```javascript
// Setup image carousel - cycle through uploaded images
const setupImageCarousel = () => {
    console.log('=== setupImageCarousel called ===');
    const items = document.querySelectorAll('.marketplace-item');
    console.log('Found marketplace items:', items.length);
    
    items.forEach((card, index) => {
      const imagesData = card.getAttribute('data-images');
      console.log(`Item ${index} - data-images:`, imagesData);
      
      if (!imagesData) {
        console.log(`Item ${index} - Skipping, no images data`);
        return;
      }
      
      try {
        const images = JSON.parse(imagesData);
        console.log(`Item ${index} - Parsed images:`, images);
        
        if (images.length <= 1) {
          console.log(`Item ${index} - Skipping, only ${images.length} image(s)`);
          return;
        }
        
        const img = card.querySelector('.item-carousel-img');
        console.log(`Item ${index} - Found img element:`, !!img);
        
        if (!img) return;
        
        let currentIndex = 0;
        let cycleInterval = null;
        
        const cycleImages = () => {
          currentIndex = (currentIndex + 1) % images.length;
          // Use formatImageUrl function to handle both local and Cloudinary URLs
          let imgUrl = formatImageUrl(images[currentIndex]);
          img.src = imgUrl;
          console.log('Cycling to image', currentIndex, ':', imgUrl);
        };
        
        // Start cycling when card comes into view
        const observer = new IntersectionObserver((entries) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              console.log('Card visible, starting carousel');
              if (!cycleInterval) {
                cycleInterval = setInterval(cycleImages, 2000); // Change image every 2 seconds
              }
            } else {
              // Stop cycling when card leaves view
              if (cycleInterval) {
                clearInterval(cycleInterval);
                cycleInterval = null;
              }
            }
          });
        });
        
        observer.observe(card);
      } catch (e) {
        console.error(`Error parsing images for item ${index}:`, e);
      }
    });
};

// Image URL formatter for JavaScript
function formatImageUrl(url) {
    if (!url) return '/static/placeholder.png';
    
    // If already a full URL, return as-is
    if (url.includes('http://') || url.includes('https://')) {
        return url;
    }
    
    // If already a Cloudinary URL, return as-is
    if (url.includes('res.cloudinary.com')) {
        return url;
    }
    
    // If local static path, ensure proper format
    if (url.includes('/static/')) {
        return url.replace(/\/+/g, '/');
    }
    
    // Check if it looks like a Cloudinary public_id (contains 'barterex/' folder structure)
    if (url.includes('barterex/')) {
        const cloudinaryCloudName = '{{ cloudinary_cloud_name }}';
        if (cloudinaryCloudName) {
          return `https://res.cloudinary.com/${cloudinaryCloudName}/image/upload/q_auto,f_auto/${url}`;
        }
    }
    
    // Otherwise treat as local filename
    return `/static/uploads/${url.replace(/^\/+|\/+$/g, '')}`;
}

// Call on page load
setupImageCarousel();
```

---

## 5. CONTEXT PROCESSOR: Passing Cloudinary Config

**File:** [app.py](app.py#L254-L280)

```python
# ✅ Context processor for cart info, CSRF token, and Cloudinary config
@app.context_processor
def inject_cart_info():
    from flask_login import current_user
    from flask_wtf.csrf import generate_csrf
    from models import Favorite
    
    context = {
        'csrf_token': generate_csrf,
        'use_cloudinary': app.config.get('USE_CLOUDINARY', False),
        'cloudinary_cloud_name': app.config.get('CLOUDINARY_CLOUD_NAME', ''),
    }
    
    if current_user.is_authenticated:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
        if cart:
            cart_count = cart.get_item_count()
        else:
            cart_count = 0
        
        # Get favorites count
        favorites_count = Favorite.query.filter_by(user_id=current_user.id).count()
        
        context.update({
            'cart_count': cart_count,
            'favorites_count': favorites_count,
        })
    else:
        context.update({
            'cart_count': 0,
            'favorites_count': 0,
        })
    
    return context
```

---

## 6. HOW TO REPLICATE IN ADMIN DASHBOARD

### Step 1: Update the Admin Route
```python
# In the admin route for items list
@admin_bp.route('/items')
@login_required
def admin_items():
    # ✅ Use joinedload to eager-load images
    items = Item.query.options(joinedload(Item.images)).all()
    return render_template('admin/dashboard.html', items=items)
```

### Step 2: Build Image Array in Template
```html
{% for item in items %}
  {% set ns = namespace(images=[]) %}
  
  {% if item.image_url %}
    {% set _ = ns.images.append(item.image_url) %}
  {% endif %}
  
  {% if item.images %}
    {% for img in item.images %}
      {% if img.image_url %}
        {% set _ = ns.images.append(img.image_url) %}
      {% endif %}
    {% endfor %}
  {% endif %}
  
  <!-- Display or store images -->
  {% if ns.images %}
    <img src="{{ ns.images[0] | image_url }}" alt="{{ item.name }}">
  {% endif %}
{% endfor %}
```

### Step 3: Use the image_url Filter
```html
<!-- Always apply the filter -->
<img src="{{ item.image_url | image_url }}" alt="{{ item.name }}">
<img src="{{ item.images[0].image_url | image_url }}" alt="{{ item.name }}">
```

### Step 4: Add Error Handling
```html
<img src="{{ item.image_url | image_url }}" 
     alt="{{ item.name }}"
     onerror="this.src='/static/placeholder.png'">
```

---

## 7. SUMMARY: Key Takeaways

| Aspect | How It Works |
|--------|-------------|
| **Route** | Uses `joinedload(Item.images)` to eager-load images |
| **Data Passing** | Sends `items` list with all image relationships loaded |
| **Template Array** | Builds `ns.images` array combining `item.image_url` and `item.images` |
| **Filtering** | Applies `\| image_url` filter to every image URL |
| **Fallback** | Uses `item.image_url or item.images[0].image_url` pattern |
| **Display** | Shows first image initially, stores all in `data-images` JSON |
| **Carousel** | JavaScript parses JSON and cycles through images |
| **Error Handling** | `onerror="this.src='/static/placeholder.png'"` attribute |
| **Cloudinary** | Filter detects and preserves Cloudinary URLs |
| **Local Files** | Filter checks disk and returns proper `/static/uploads/` path |

---

## 8. WORKING EXAMPLES BY LOCATION

### ✅ Marketplace Grid (Working)
- **File:** [templates/marketplace.html](templates/marketplace.html#L1670-L1720)
- **Route:** [routes/marketplace.py](routes/marketplace.py#L29-L95)
- **Status:** ✅ Images display correctly with carousel

### ✅ Item Detail Slideshow (Working)
- **File:** [templates/item_detail.html](templates/item_detail.html#L723-L950)
- **Route:** [routes/marketplace.py](routes/marketplace.py#L116-L150)
- **Status:** ✅ Full slideshow with thumbnails and navigation

### ✅ Related Items (Working)
- **File:** [templates/item_detail.html](templates/item_detail.html#L950-L990)
- **Status:** ✅ First image from `item.images[0]` displays correctly

### ✅ Cart/Checkout (Working)
- **File:** [templates/cart.html](templates/cart.html#L1122), [templates/checkout.html](templates/checkout.html#L590)
- **Status:** ✅ Uses `item.image_url or item.images[0].image_url` pattern

---

## Notes for Admin Dashboard Implementation

1. **Eager Loading is Critical:** Always use `joinedload(Item.images)` in routes to prevent N+1 queries
2. **Filter Every URL:** Apply `| image_url` to every image URL in templates
3. **Namespace Array:** Use the Jinja namespace trick to combine multiple image sources
4. **Error Attributes:** Always include `onerror="this.src='/static/placeholder.png'"` on `<img>` tags
5. **Conditional Display:** Check `{% if item.images %}` before accessing `item.images[0]`
6. **JSON for Carousel:** If implementing carousel/slideshow, use `| tojson` to pass images to JavaScript
7. **Cloudinary Detection:** The `image_url` filter automatically handles Cloudinary URLs

