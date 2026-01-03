"""
Transaction Clarity Module
Handles order receipts, transaction explanations, and delivery timelines
"""

from datetime import datetime, timedelta
from flask import render_template_string
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from io import BytesIO
from logger_config import setup_logger

logger = setup_logger(__name__)

# ==================== DELIVERY TIMELINES ====================

DELIVERY_TIMELINES = {
    'home delivery': {
        'min_days': 3,
        'max_days': 7,
        'description': 'Order will be delivered to your home address'
    },
    'pickup': {
        'min_days': 1,
        'max_days': 2,
        'description': 'Order ready for pickup at selected station'
    }
}

def calculate_estimated_delivery(delivery_method):
    """
    Calculate estimated delivery date based on delivery method
    
    Args:
        delivery_method: 'home delivery' or 'pickup'
    
    Returns:
        datetime object representing estimated delivery
    """
    try:
        if delivery_method not in DELIVERY_TIMELINES:
            delivery_method = 'home delivery'
        
        timeline = DELIVERY_TIMELINES[delivery_method]
        # Use average of min and max days
        avg_days = (timeline['min_days'] + timeline['max_days']) / 2
        estimated_date = datetime.utcnow() + timedelta(days=int(avg_days))
        
        logger.info(f"Calculated delivery estimate - Method: {delivery_method}, Date: {estimated_date}")
        return estimated_date
    except Exception as e:
        logger.error(f"Error calculating delivery date: {str(e)}", exc_info=True)
        return datetime.utcnow() + timedelta(days=5)

def get_delivery_explanation(delivery_method):
    """
    Get user-friendly explanation of delivery method and timeline
    
    Args:
        delivery_method: 'home delivery' or 'pickup'
    
    Returns:
        dict with explanation and timeline details
    """
    if delivery_method not in DELIVERY_TIMELINES:
        delivery_method = 'home delivery'
    
    timeline = DELIVERY_TIMELINES[delivery_method]
    return {
        'method': delivery_method,
        'description': timeline['description'],
        'min_days': timeline['min_days'],
        'max_days': timeline['max_days'],
        'full_text': f"{timeline['description']} within {timeline['min_days']}-{timeline['max_days']} business days"
    }

# ==================== TRANSACTION EXPLANATIONS ====================

def generate_transaction_explanation(order, user):
    """
    Generate a clear explanation of the transaction for the user
    
    Args:
        order: Order object
        user: User object
    
    Returns:
        dict with transaction details and explanations
    """
    try:
        # Build items list with safe access
        items_list = []
        for item in order.items:
            try:
                if item.item:  # Check if item relationship exists
                    items_list.append({
                        'name': item.item.name or 'Unknown Item',
                        'condition': item.item.condition or 'Unknown',
                        'value': f"₦{item.item.value:,.0f}" if item.item.value else '₦0',
                        'location': item.item.location or 'Unknown'
                    })
            except Exception as item_error:
                logger.error(f"Error processing item {item.id}: {str(item_error)}")
                items_list.append({
                    'name': 'Error Loading Item',
                    'condition': 'N/A',
                    'value': '₦0',
                    'location': 'N/A'
                })
        
        explanation = {
            'order_number': order.order_number,
            'date_ordered': order.date_ordered.strftime('%d %b %Y, %H:%M'),
            'delivery_method': get_delivery_explanation(order.delivery_method),
            'estimated_delivery': order.estimated_delivery_date.strftime('%d %b %Y') if order.estimated_delivery_date else 'TBD',
            'status': order.status,
            'status_explanation': get_status_explanation(order.status),
            
            # Credit details
            'credits': {
                'balance_before': f"₦{order.credits_balance_before:,.0f}",
                'total_items_value': f"₦{order.total_credits:,.0f}",
                'credits_used': f"₦{order.credits_used:,.0f}",
                'balance_after': f"₦{order.credits_balance_after:,.0f}",
                'explanation': f"You had ₦{order.credits_balance_before:,.0f} credits. After this order (₦{order.credits_used:,.0f}), your balance is now ₦{order.credits_balance_after:,.0f}."
            },
            
            # Items summary
            'items_count': len(order.items),
            'items': items_list
        }
        
        logger.info(f"Generated transaction explanation - Order: {order.order_number}, Items: {len(items_list)}")
        return explanation
    except Exception as e:
        logger.error(f"Error generating transaction explanation: {str(e)}", exc_info=True)
        # Return a minimal dict instead of empty dict so template doesn't break
        return {
            'order_number': getattr(order, 'order_number', 'Unknown'),
            'items': [],
            'items_count': 0,
            'credits': {
                'balance_before': '₦0',
                'total_items_value': '₦0',
                'credits_used': '₦0',
                'balance_after': '₦0',
                'explanation': 'Error loading transaction details'
            },
            'status_explanation': {
                'title': 'Unknown Status',
                'description': 'Unable to load order status',
                'what_happens': 'Please try again later',
                'icon': '❓'
            }
        }

def get_status_explanation(status):
    """
    Get user-friendly explanation of order status
    
    Args:
        status: Order status string
    
    Returns:
        dict with status details and what happens next
    """
    explanations = {
        'Pending': {
            'title': 'Order Received',
            'description': 'Your order has been received and is being reviewed',
            'what_happens': 'We will prepare your items and contact you soon',
            'icon': '📋'
        },
        'Processing': {
            'title': 'Processing',
            'description': 'Your items are being prepared for delivery',
            'what_happens': 'Your order will be ready for shipping soon',
            'icon': '⚙️'
        },
        'Shipped': {
            'title': 'On the Way',
            'description': 'Your order has been shipped and is on its way to you',
            'what_happens': 'You will receive your items soon',
            'icon': '🚚'
        },
        'Delivered': {
            'title': 'Delivered',
            'description': 'Your order has been successfully delivered',
            'what_happens': 'Enjoy your items!',
            'icon': '✅'
        },
        'Cancelled': {
            'title': 'Cancelled',
            'description': 'Your order has been cancelled',
            'what_happens': 'Your credits have been refunded',
            'icon': '❌'
        }
    }
    
    return explanations.get(status, {
        'title': status,
        'description': f'Order status: {status}',
        'what_happens': 'Check back for updates',
        'icon': '📊'
    })

# ==================== RECEIPT GENERATION ====================

def generate_pdf_receipt(order, user):
    """
    Generate a PDF receipt for the order
    
    Args:
        order: Order object
        user: User object
    
    Returns:
        BytesIO object containing PDF data
    """
    try:
        # Create PDF buffer
        buffer = BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch,
            title=f"Receipt-{order.order_number}"
        )
        
        # Container for PDF elements
        elements = []
        
        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#054e97'),
            spaceAfter=10,
            alignment=1  # Center
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#054e97'),
            spaceAfter=8,
            spaceBefore=8
        )
        
        # Title
        elements.append(Paragraph("🛒 BARTEREX TRANSACTION RECEIPT", title_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Order header info
        order_info = [
            ['Order Number:', order.order_number],
            ['Date:', order.date_ordered.strftime('%d %B %Y, %H:%M')],
            ['Customer:', user.username],
            ['Email:', user.email],
        ]
        
        order_table = Table(order_info, colWidths=[2*inch, 4*inch])
        order_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f0f7')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        elements.append(order_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Delivery Information
        elements.append(Paragraph("📦 Delivery Information", heading_style))
        delivery_info = [
            ['Method:', order.delivery_method.title()],
            ['Estimated Delivery:', order.estimated_delivery_date.strftime('%d %B %Y') if order.estimated_delivery_date else 'To be determined'],
            ['Status:', order.status],
        ]
        
        if order.delivery_address:
            delivery_info.append(['Address:', order.delivery_address])
        
        delivery_table = Table(delivery_info, colWidths=[2*inch, 4*inch])
        delivery_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f0f7')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        elements.append(delivery_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Items ordered
        elements.append(Paragraph("📋 Items in This Order", heading_style))
        items_data = [['Item Name', 'Condition', 'Value (₦)']]
        
        for item in order.items:
            items_data.append([
                item.item.name[:30],
                item.item.condition,
                f"₦{item.item.value:,.0f}"
            ])
        
        items_data.append(['', 'TOTAL:', f"₦{order.total_credits:,.0f}"])
        
        items_table = Table(items_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#054e97')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f0f7')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Credits summary
        elements.append(Paragraph("💰 Credit Transaction Summary", heading_style))
        credits_data = [
            ['Your Balance Before Order:', f"₦{order.credits_balance_before:,.0f}"],
            ['Credits Used in This Order:', f"₦{order.credits_used:,.0f}"],
            ['Your Balance After Order:', f"₦{order.credits_balance_after:,.0f}"],
        ]
        
        credits_table = Table(credits_data, colWidths=[3.5*inch, 2.5*inch])
        credits_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f0f7')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        elements.append(credits_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Footer
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.grey,
            alignment=1
        )
        elements.append(Paragraph(
            "Thank you for using Barterex! For support, visit our website or contact us.<br/>" +
            f"Generated on {datetime.utcnow().strftime('%d %B %Y at %H:%M')}",
            footer_style
        ))
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        logger.info(f"Generated PDF receipt - Order: {order.order_number}")
        return buffer
    except Exception as e:
        logger.error(f"Error generating PDF receipt: {str(e)}", exc_info=True)
        return None

def generate_html_receipt(order, user):
    """
    Generate an HTML receipt for the order (for email)
    
    Args:
        order: Order object
        user: User object
    
    Returns:
        HTML string
    """
    try:
        transaction_exp = generate_transaction_explanation(order, user)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #054e97 0%, #0066cc 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 20px; }}
                .section {{ margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #054e97; }}
                .section h3 {{ margin-top: 0; color: #054e97; }}
                .info-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #ddd; }}
                .info-row:last-child {{ border-bottom: none; }}
                .label {{ font-weight: bold; color: #054e97; }}
                .value {{ color: #333; }}
                .items-table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                .items-table th {{ background: #054e97; color: white; padding: 10px; text-align: left; }}
                .items-table td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
                .items-table tr:nth-child(even) {{ background: #f8f9fa; }}
                .total {{ font-weight: bold; font-size: 16px; color: #054e97; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🛒 Barterex Transaction Receipt</h2>
                    <p>Order #{order.order_number}</p>
                </div>
                
                <div class="section">
                    <h3>📋 Order Information</h3>
                    <div class="info-row">
                        <span class="label">Order Date:</span>
                        <span class="value">{transaction_exp['date_ordered']}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Status:</span>
                        <span class="value">{order.status}</span>
                    </div>
                </div>
                
                <div class="section">
                    <h3>📦 Delivery Information</h3>
                    <div class="info-row">
                        <span class="label">Method:</span>
                        <span class="value">{transaction_exp['delivery_method']['description']}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Estimated Delivery:</span>
                        <span class="value">{transaction_exp['estimated_delivery']}</span>
                    </div>
                </div>
                
                <div class="section">
                    <h3>📋 Items in Your Order</h3>
                    <table class="items-table">
                        <thead>
                            <tr>
                                <th>Item Name</th>
                                <th>Condition</th>
                                <th>Value</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        
        for item in transaction_exp['items']:
            html += f"""
                            <tr>
                                <td>{item['name']}</td>
                                <td>{item['condition']}</td>
                                <td>{item['value']}</td>
                            </tr>
            """
        
        html += f"""
                        </tbody>
                    </table>
                    <div class="info-row total">
                        <span>Total Value:</span>
                        <span>{transaction_exp['credits']['total_items_value']}</span>
                    </div>
                </div>
                
                <div class="section">
                    <h3>💰 Credit Transaction Summary</h3>
                    <div class="info-row">
                        <span class="label">Balance Before:</span>
                        <span class="value">{transaction_exp['credits']['balance_before']}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Credits Used:</span>
                        <span class="value">{transaction_exp['credits']['credits_used']}</span>
                    </div>
                    <div class="info-row total">
                        <span class="label">Balance After:</span>
                        <span class="value">{transaction_exp['credits']['balance_after']}</span>
                    </div>
                </div>
                
                <div class="footer">
                    <p>Thank you for using Barterex!</p>
                    <p>For support, visit our website or contact us.</p>
                    <p>Generated on {datetime.utcnow().strftime('%d %B %Y at %H:%M')}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        logger.info(f"Generated HTML receipt - Order: {order.order_number}")
        return html
    except Exception as e:
        logger.error(f"Error generating HTML receipt: {str(e)}", exc_info=True)
        return None
