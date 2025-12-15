# AI Price Estimator - Debugging Guide

## Issue: Estimator Button Not Appearing

If the "Estimate My Item's Value" button doesn't appear after filling the form, follow these steps:

---

## Step 1: Check Browser Console

1. Open your browser (Chrome, Firefox, etc.)
2. Press **F12** to open Developer Tools
3. Click the **Console** tab
4. Go to `/upload` page
5. Fill the form completely
6. Watch the console output

**What to look for:**
```
Form field check: {
  nameInput: "Your Item Name",
  descriptionInput: "Your description here",
  conditionSelect: "good",
  categorySelect: "electronics",
  selectedFiles: 1
}
Has all fields: true
```

If you see `Has all fields: true`, the estimator SHOULD appear.

If you see `Has all fields: false`, check which field is missing:
- `nameInput: ""` - Item name is empty
- `descriptionInput: ""` - Description is empty or < 10 characters
- `conditionSelect: ""` - Condition dropdown not selected
- `categorySelect: ""` - Category dropdown not selected
- `selectedFiles: 0` - No images uploaded

---

## Step 2: Check if Form Fields Are Found

Look for this in console:
```
Some form fields not found in DOM
```

If you see this, the form field names might be different. Continue to Step 3.

---

## Step 3: Inspect Form Fields

1. In Developer Tools, right-click on the Item Name input field
2. Click "Inspect" or "Inspect Element"
3. Look at the HTML code
4. Find the `name` attribute - it should say `name="name"`

Example:
```html
<input class="form-input" name="name" type="text">
```

Do the same for:
- Description (should have `name="description"`)
- Condition (should have `name="condition"`)
- Category (should have `name="category"`)

**If the names are different**, report them to the developer.

---

## Step 4: Check if Estimator Section Exists

1. In Developer Tools, press **Ctrl+F** (or Cmd+F on Mac)
2. Search for `aiEstimatorSection`
3. You should see the HTML for the estimator section

If it's not there, the HTML wasn't properly added to the page.

---

## Step 5: Check for JavaScript Errors

In the Console tab, look for red error messages that might say:
- `Uncaught SyntaxError`
- `Uncaught ReferenceError`
- `Cannot read property`

If you see errors, take a screenshot and report them.

---

## Step 6: Manual Test

In the browser console, type:
```javascript
checkEstimatorAvailability()
```

Press Enter. You should see the form field check output.

Then type:
```javascript
aiEstimatorSection.style.display
```

It should return either `"block"` or `"none"`.

---

## Step 7: Check Network Tab

1. Open Developer Tools
2. Go to **Network** tab
3. Click "Upload" form
4. Check if there are any failed network requests
5. Look for requests to `/api/estimate-price` or other API calls

---

## Quick Checklist

- [ ] Item Name: Filled with at least 1 character
- [ ] Description: Filled with at least 10 characters
- [ ] Condition: Selected from dropdown (not blank)
- [ ] Category: Selected from dropdown (not blank)
- [ ] Image: At least 1 image uploaded
- [ ] Browser console shows no errors
- [ ] Console shows "Has all fields: true"

---

## Common Issues & Solutions

### Issue: Estimator section doesn't appear after filling all fields

**Solution 1:** Clear browser cache and refresh
```
Ctrl+Shift+Delete (or Cmd+Shift+Delete on Mac) → Clear cache → Refresh page
```

**Solution 2:** Make sure you filled at least 10 characters in description
- Too short descriptions won't trigger the estimator

**Solution 3:** Make sure an image is uploaded
- The estimator requires at least 1 image

### Issue: Button appears but is greyed out / disabled

**Solution:** Click it! It should be clickable.

### Issue: Click button but nothing happens

1. Check browser console for errors
2. Make sure API keys are set in `.env`
3. Restart Flask server
4. Refresh the page

### Issue: Button shows, clicks work, but no results appear

1. Check browser console for errors
2. Look at Flask console output for error messages
3. Check network tab to see if API request was made

---

## Troubleshooting Steps (In Order)

1. **Open DevTools Console** - Check for error messages
2. **Refresh Page** - Sometimes JS doesn't load properly
3. **Fill Form Slowly** - Wait after each field for JavaScript to process
4. **Check All Fields** - Make sure ALL fields are filled:
   - Name: ✅ Has text
   - Description: ✅ Has 10+ characters
   - Condition: ✅ Selected (not blank)
   - Category: ✅ Selected (not blank)
   - Image: ✅ At least 1 uploaded
5. **Check Console Output** - Look for `Has all fields: true`
6. **Check Network Tab** - See if API calls are working

---

## What to Report

If nothing works after these steps, provide:

1. **Screenshot of console output** showing the form field check
2. **Screenshot of the form** with all fields filled
3. **Screenshot of DevTools Console** showing any errors
4. **Flask console output** if there are any errors

---

## Still Not Working?

1. **Check API Keys in `.env`:**
   - Open `.env` file
   - Verify `OPENAI_API_KEY` and `GOOGLE_API_KEY` are set
   - Restart Flask

2. **Check if services module loads:**
   - In Flask console, should see no import errors
   - Check `services/ai_price_estimator.py` exists

3. **Check if route is registered:**
   - In Flask console, look for routes list
   - Should see `/api/estimate-price` endpoint

---

## Testing Script

You can run this in the browser console to test everything:

```javascript
// Test 1: Check if functions exist
console.log('checkEstimatorAvailability exists:', typeof checkEstimatorAvailability === 'function');
console.log('estimatePrice exists:', typeof estimatePrice === 'function');
console.log('displayPriceEstimate exists:', typeof displayPriceEstimate === 'function');

// Test 2: Check form fields
const nameInput = document.querySelector('input[name="name"]') || document.getElementById('name');
const descriptionInput = document.querySelector('textarea[name="description"]') || document.getElementById('description');
const conditionSelect = document.querySelector('select[name="condition"]') || document.getElementById('condition');
const categorySelect = document.querySelector('select[name="category"]') || document.getElementById('category');

console.log('Form fields found:');
console.log('- Name input:', nameInput ? 'YES' : 'NO');
console.log('- Description input:', descriptionInput ? 'YES' : 'NO');
console.log('- Condition select:', conditionSelect ? 'YES' : 'NO');
console.log('- Category select:', categorySelect ? 'YES' : 'NO');

// Test 3: Check estimator section
const aiEstimatorSection = document.getElementById('aiEstimatorSection');
console.log('Estimator section exists:', aiEstimatorSection ? 'YES' : 'NO');
console.log('Estimator section display:', aiEstimatorSection ? aiEstimatorSection.style.display : 'N/A');

// Test 4: Run check
checkEstimatorAvailability();
```

Run this and share the output if you need help!

---

## Success Indicators

✅ Console shows: `Has all fields: true`
✅ Purple estimator section becomes visible
✅ Can click the estimator button
✅ Button shows loading spinner when clicked
✅ Results appear after 4-12 seconds
✅ Price and credits display correctly

---

Good luck debugging! 🔍
