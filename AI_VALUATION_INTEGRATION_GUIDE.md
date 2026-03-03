# 🔧 INTEGRATION GUIDE: Adding Provisional Credits to Upload Flow

## 🎯 WHAT NEEDS TO HAPPEN

When a user uploads an item AFTER valuation, the system needs to:

1. **Store AI valuation data** from the form
2. **Create ItemValuation record** for audit trail
3. **Issue provisional credits** to user account
4. **Mark item for verification** (not public yet)
5. **Send user notification** about provisional credits

---

## 📝 MODIFICATIONS REQUIRED

### MODIFICATION 1: Update Upload Route (routes/items.py)

Find the `/upload` route's form submission section and modify it to:

```python
@items_bp.route('/upload', methods=['GET', 'POST'])
@login_required
@handle_errors
def upload_item():
    # ... existing code ...
    
    if form.validate_on_submit() and not image_validation_errors:
        # Get valuation data from form (user submitted after AI valuation)
        # This comes from hidden form fields that should be added to the template
        ai_estimated_value = request.form.get('ai_estimated_value', type=float)
        ai_confidence = request.form.get('ai_confidence', '')
        provisional_credit_value = request.form.get('provisional_credit', type=float)
        ai_analysis = request.form.get('ai_analysis', '')
        
        new_item = Item(
            name=form.name.data,
            description=form.description.data,
            condition=form.condition.data,
            category=form.category.data,
            user_id=current_user.id,
            uploaded_by_id=current_user.id,
            location=current_user.state,
            is_available=False,
            is_approved=False,
            status='pending',
            
            # NEW: AI VALUATION DATA
            ai_estimated_value=ai_estimated_value,
            ai_confidence=ai_confidence,
            provisional_credit_value=provisional_credit_value,
            ai_analysis=ai_analysis,
            verification_status='valuated',  # Has been valuated by AI
        )
        db.session.add(new_item)
        db.session.flush()  # Get the item ID
        
        # ... image upload code ...
        
        # After images are uploaded successfully:
        if not upload_error_occurred and uploaded_images:
            try:
                # ISSUE PROVISIONAL CREDITS
                if provisional_credit_value and provisional_credit_value > 0:
                    current_user.credits += provisional_credit_value
                    new_item.provisional_credits_issued = True
                    new_item.provisional_credits_issued_at = datetime.utcnow()
                    
                    # Create audit record
                    from models import CreditTransaction
                    transaction = CreditTransaction(
                        user_id=current_user.id,
                        amount=provisional_credit_value,
                        type='provisional_credit',
                        description=f'Provisional credit for item: {new_item.name}',
                        related_item_id=new_item.id,
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(transaction)
                
                db.session.commit()
                
                # Send notification to user
                notification_msg = (
                    f"✅ Great! Your item '{new_item.name}' has been valued at ${new_item.ai_estimated_value:.2f}. "
                    f"You've received ${provisional_credit_value:.2f} in provisional credits. "
                    f"After physical verification at our pickup station, you'll get the full value!"
                )
                create_notification(current_user.id, notification_msg)
                
                logger.info(f"Item uploaded with valuation - Item: {new_item.id}, "
                           f"AI Value: ${ai_estimated_value}, "
                           f"Provisional Credit: ${provisional_credit_value}, "
                           f"User: {current_user.username}")
                
                flash(f'✅ Success! Your item valued at ${ai_estimated_value:.2f}. '
                      f'${provisional_credit_value:.2f} provisional credit added!', "success")
                return redirect(url_for('marketplace.marketplace'))
                
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error issuing provisional credits: {str(e)}")
                flash('Item uploaded but there was an error issuing credits. Please contact support.', 'warning')
                return redirect(url_for('marketplace.marketplace'))
        # ... rest of error handling ...
```

---

### MODIFICATION 2: Update Upload Template (templates/upload.html)

Add hidden fields to pass valuation data to the server:

```html
<!-- Add this inside the form tag, after existing fields -->
<form method="POST" enctype="multipart/form-data" id="uploadForm">
  {{ form.hidden_tag() }}
  
  <!-- ... existing form fields ... -->
  
  <!-- HIDDEN VALUATION DATA (populated by JavaScript) -->
  <input type="hidden" name="ai_estimated_value" id="ai_estimated_value" value="">
  <input type="hidden" name="ai_confidence" id="ai_confidence" value="">
  <input type="hidden" name="provisional_credit" id="provisional_credit" value="">
  <input type="hidden" name="ai_analysis" id="ai_analysis" value="">
  
  <!-- ... rest of form ... -->
</form>

<!-- In the valuation JavaScript section, update confirmSubmitBtn handler: -->
<script>
  confirmSubmitBtn.addEventListener('click', function(e) {
    e.preventDefault();
    
    // Populate hidden fields with valuation data before submitting
    document.getElementById('ai_estimated_value').value = data.estimated_price;
    document.getElementById('ai_confidence').value = data.confidence;
    document.getElementById('provisional_credit').value = data.provisional_credit;
    document.getElementById('ai_analysis').value = data.analysis;
    
    // Now submit the form
    submitBtn.click();
  });
</script>
```

---

## 🗂️ DATABASE MODELS TO CREATE/UPDATE

### Model 1: ItemValuation (NEW)

Create a new audit model to track all valuations:

```python
# Add to models.py

class ItemValuation(db.Model):
    """
    Audit trail for all item valuations.
    Records AI estimates, manual adjustments, and verification results.
    """
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id', ondelete='CASCADE'), nullable=False, index=True)
    item = db.relationship('Item', backref='valuations')
    
    # AI Valuation
    ai_estimated_value = db.Column(db.Float, nullable=True)
    ai_confidence = db.Column(db.String(20), nullable=True)  # HIGH, MEDIUM, LOW
    ai_analysis = db.Column(db.Text, nullable=True)
    ai_condition_score = db.Column(db.Float, nullable=True)
    ai_market_listings = db.Column(db.Integer, default=0)
    valuated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Provisional Credits
    provisional_credit_value = db.Column(db.Float, nullable=True)
    provisional_issued_at = db.Column(db.DateTime, nullable=True)
    
    # Physical Verification
    verified_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    verification_result = db.Column(db.String(20), nullable=True)  # verified, rejected, needs_adjustment
    verification_notes = db.Column(db.Text, nullable=True)
    
    # Final Credit After Verification
    final_credit_value = db.Column(db.Float, nullable=True)
    adjustment_reason = db.Column(db.Text, nullable=True)  # Why it differs from AI estimate
    
    # Status tracking
    status = db.Column(db.String(30), default='valuated')  # valuated → pending_verification → verified/rejected
    
    verified_by = db.relationship('User', foreign_keys=[verified_by_id])
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ItemValuation Item:{self.item_id} Value:${self.ai_estimated_value}>'
```

### Model 2: CreditTransaction (Update existing)

Make sure `CreditTransaction` has `related_item_id`:

```python
class CreditTransaction(db.Model):
    """
    Track all credit transactions for audit trail.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', back_populates='transactions')
    
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(50), nullable=False)  # purchase, refund, provisional_credit, verified_credit, etc.
    description = db.Column(db.String(255), nullable=True)
    related_item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=True)  # NEW FIELD
    related_order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<CreditTransaction User:{self.user_id} Amount:{self.amount} Type:{self.type}>'
```

---

## 🚀 COMPLETE UPLOAD FLOW WITH VALUATION

```
USER JOURNEY:
┌─────────────────────────────────────────────────┐
│ 1. Visit /upload                                 │
├─────────────────────────────────────────────────┤
│ 2. Fill form:                                    │
│    • Item Name                                   │
│    • Description                                 │
│    • Condition                                   │
│    • Category                                    │
│    • Images (1-6)                               │
├─────────────────────────────────────────────────┤
│ 3. Click "💎 VALUATE ITEM"                     │
│    ↓                                             │
│    POST /api/valuate-item                       │
│    ↓                                             │
│    Returns: estimated_price, provisional_credit │
│    ↓                                             │
│    Display results to user                      │
├─────────────────────────────────────────────────┤
│ 4. User clicks "Confirm & Upload"               │
│    ↓                                             │
│ 5. Hidden fields populated with valuation data   │
│    ↓                                             │
│ 6. Form submitted via POST /upload               │
├─────────────────────────────────────────────────┤
│ 7. Server-side processing:                      │
│    • Create Item record with AI valuation data   │
│    • Upload images to Cloudinary                │
│    • Issue provisional credits                  │
│    • Create CreditTransaction record            │
│    • Create ItemValuation audit record          │
│    • Send notification to user                  │
├─────────────────────────────────────────────────┤
│ 8. User redirected to marketplace               │
│    • User has: original_credits + provisional   │
│    • User can NOW purchase other items          │
│    • Item appears in admin (pending_verification)│
├─────────────────────────────────────────────────┤
│ 9. Item goes to pickup station for verification │
│    • Admin/Staff verify condition                │
│    • Confirm or dispute AI valuation            │
│    • Adjust credit if needed                    │
│    • Update verification_result                 │
├─────────────────────────────────────────────────┤
│ 10. Final credit issued:                        │
│     • If VERIFIED: Full credit released         │
│     • If REJECTED: Purchase reversed, credits   │
│       removed from user account, user notified  │
└─────────────────────────────────────────────────┘
```

---

## 💻 CODE REFERENCE

### Function: Issue Provisional Credits

```python
def issue_provisional_credits(item, user, provisional_amount):
    """Issue provisional credits to user after valuation"""
    try:
        # Add to user's credits
        user.credits += provisional_amount
        
        # Mark item as credits issued
        item.provisional_credits_issued = True
        item.provisional_credits_issued_at = datetime.utcnow()
        
        # Create audit transaction
        trans = CreditTransaction(
            user_id=user.id,
            amount=provisional_amount,
            type='provisional_credit',
            description=f'Provisional credit for {item.name}',
            related_item_id=item.id,
            timestamp=datetime.utcnow()
        )
        db.session.add(trans)
        
        # Create valuation audit record
        valuation = ItemValuation(
            item_id=item.id,
            ai_estimated_value=item.ai_estimated_value,
            ai_confidence=item.ai_confidence,
            ai_analysis=item.ai_analysis,
            provisional_credit_value=provisional_amount,
            provisional_issued_at=datetime.utcnow(),
            status='valuated'
        )
        db.session.add(valuation)
        
        db.session.commit()
        
        logger.info(f"Provisional credits issued - User: {user.username}, Amount: ${provisional_amount}, Item: {item.id}")
        return True
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error issuing provisional credits: {str(e)}")
        raise
```

### Function: Verify and Issue Final Credits

```python
def verify_and_finalize_credits(item, verified_by_user, verification_result, final_value=None):
    """
    Complete item verification and issue final credits.
    Called when admin/staff verifies item at pickup station.
    """
    try:
        if verification_result == 'verified':
            # Item verified! Issue final credits if different from provisional
            if final_value is None:
                final_value = item.ai_estimated_value
            
            # Get difference from provisional
            difference = final_value - item.provisional_credit_value
            
            if difference > 0:
                # Top-up: add additional credits
                item.user.credits += difference
                trans_type = 'verified_credit_topup'
            elif difference < 0:
                # Reduction: remove excess credits (must exist)
                item.user.credits += difference  # subtracts
                trans_type = 'verified_credit_reduction'
            else:
                trans_type = 'verified_credit_confirmed'
            
            # Create transaction for final credit
            trans = CreditTransaction(
                user_id=item.user_id,
                amount=final_value,
                type=trans_type,
                description=f'Final verified credit for {item.name}',
                related_item_id=item.id
            )
            db.session.add(trans)
            
            # Mark item as verified
            item.final_credit_value = final_value
            item.verification_result = 'verified'
            item.verified_at = datetime.utcnow()
            item.verified_by_id = verified_by_user.id
            item.verification_status = 'verified'
            item.is_available = True  # Can now be listed
            
        elif verification_result in ['rejected', 'failed_condition']:
            # Item rejected! Remove provisional credits
            item.user.credits -= item.provisional_credit_value
            
            # Create transaction for credit removal
            trans = CreditTransaction(
                user_id=item.user_id,
                amount=-item.provisional_credit_value,
                type='provisional_credit_refunded',
                description=f'Credit reversed: {item.name} failed verification',
                related_item_id=item.id
            )
            db.session.add(trans)
            
            # Mark item as rejected
            item.verification_result = verification_result
            item.verification_status = 'rejected'
            item.verified_at = datetime.utcnow()
            item.verified_by_id = verified_by_user.id
            item.is_available = False
        
        db.session.commit()
        
        logger.info(f"Item verification completed - Item: {item.id}, Result: {verification_result}, User: {item.user.username}")
        
        # Send notification
        if verification_result == 'verified':
            message = f"✅ Your item '{item.name}' has been verified! Final credit: ${final_value:.2f}"
        else:
            message = f"❌ Your item '{item.name}' did not pass verification. Credits have been refunded."
        
        create_notification(item.user_id, message)
        
        return True
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error completing item verification: {str(e)}")
        raise
```

---

## 🧪 TESTING CHECKLIST

- [ ] Upload page loads with "Valuate" button
- [ ] Valuation returns realistic prices
- [ ] Hidden fields populate with valuation data
- [ ] Form submits after "Confirm & Upload"
- [ ] Item created in database with AI valuation data
- [ ] Provisional credits added to user account
- [ ] Credit transaction logged
- [ ] User notification sent
- [ ] Item status = "pending_verification"
- [ ] Item NOT visible in marketplace yet
- [ ] Admin dashboard shows item for verification
- [ ] Admin can approve/reject and adjust credits
- [ ] Final credits issued/removed correctly

---

## 🔗 RELATED FILES

- `services/ai_price_estimator.py` - AI valuation engine
- `routes/items.py` - Upload route with provisional credits
- `templates/upload.html` - Upload form with valuation UI
- `models.py` - Database models with new fields
