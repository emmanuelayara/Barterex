from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user
from models import ContactMessage
from app import db
from logger_config import setup_logger
from markupsafe import escape
from error_handlers import handle_errors
import datetime

logger = setup_logger(__name__)

contact_bp = Blueprint('contact', __name__)


@contact_bp.route('/contact-form', methods=['GET', 'POST'])
@handle_errors
def contact_form():
    """Display and handle contact form submissions"""
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            message_text = request.form.get('message', '').strip()
            
            # Validate inputs
            if not name or len(name) < 2 or len(name) > 120:
                flash('Name must be between 2 and 120 characters.', 'danger')
                return render_template('contact_form.html')
            
            if not email or '@' not in email or len(email) > 120:
                flash('Please provide a valid email address.', 'danger')
                return render_template('contact_form.html')
            
            if not message_text or len(message_text) < 10 or len(message_text) > 5000:
                flash('Message must be between 10 and 5000 characters.', 'danger')
                return render_template('contact_form.html')
            
            # Escape inputs for security (prevent XSS)
            name = escape(name)
            email = escape(email)
            message_text = escape(message_text)
            
            # Create ContactMessage instance
            contact_message = ContactMessage(
                name=name,
                email=email,
                message=message_text,
                user_id=current_user.id if current_user.is_authenticated else None,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', '')[:500],
                status='pending',
                is_read=False
            )
            
            # Save to database
            db.session.add(contact_message)
            db.session.commit()
            
            logger.info(f"Contact message received from {name} ({email}) - ID: {contact_message.id}")
            flash('Thank you for your message! We will get back to you shortly.', 'success')
            
            return redirect(url_for('contact.contact_success', message_id=contact_message.id))
            
        except Exception as e:
            db.session.rollback()
        logger.error(f"Error processing contact form: {e}", exc_info=True)
    
    # GET request - display the form
    return render_template('contact_form.html')


@contact_bp.route('/contact-success/<int:message_id>', methods=['GET'])
@handle_errors
def contact_success(message_id):
    """Display success page after contact form submission"""
    try:
        contact_message = ContactMessage.query.get_or_404(message_id)
        return render_template('contact_success.html', message=contact_message)
    except Exception as e:
        logger.error(f"Error retrieving contact message {message_id}: {e}", exc_info=True)
        flash('Could not retrieve message details.', 'danger')
        return redirect(url_for('marketplace.home'))
