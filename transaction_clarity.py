"""
Transaction Clarity Module
Handles order receipts, transaction explanations, and delivery timelines
"""

from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape
from flask import render_template_string
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image, KeepTogether
from io import BytesIO
from logger_config import setup_logger

logger = setup_logger(__name__)

# ==================== DELIVERY TIMELINES ====================

DELIVERY_TIMELINES = {
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
        delivery_method: 'pickup'
    
    Returns:
        datetime object representing estimated delivery
    """
    if delivery_method not in DELIVERY_TIMELINES:
        raise ValueError('Only verification-centre collection is available.')
    timeline = DELIVERY_TIMELINES[delivery_method]
    avg_days = (timeline['min_days'] + timeline['max_days']) / 2
    return datetime.utcnow() + timedelta(days=int(avg_days))

def get_delivery_explanation(delivery_method):
    """
    Get user-friendly explanation of delivery method and timeline
    
    Args:
        delivery_method: 'pickup', or a retired method on an archived order
    
    Returns:
        dict with explanation and timeline details
    """
    if delivery_method not in DELIVERY_TIMELINES:
        return {
            'method': 'Retired test booking',
            'description': 'This booking cannot be fulfilled. Contact support.',
            'min_days': None,
            'max_days': None,
            'full_text': 'This booking cannot be fulfilled. Contact support.',
        }
    
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
                        'item_number': item.item.item_number or 'N/A',
                        'condition': item.item.condition or 'Unknown',
                        'value': f"₦{item.item.value:,.0f}" if item.item.value else '₦0',
                        'location': item.item.location or 'Unknown'
                    })
            except Exception as item_error:
                logger.error(f"Error processing item {item.id}: {str(item_error)}")
                items_list.append({
                    'name': 'Error Loading Item',
                    'item_number': 'N/A',
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
        'Awaiting Final Acceptance': {
            'title': 'Review Final Terms',
            'description': 'Verification complete.',
            'what_happens': 'Review and accept below to pay.',
            'icon': '📋'
        },
        'Awaiting Service Fee': {
            'title': 'Service Fee Awaiting Payment',
            'description': 'Final terms accepted.',
            'what_happens': 'Pay the service fee below.',
            'icon': '📋'
        },
        'Pending': {
            'title': 'Order Received',
            'description': 'Your order has been received and is being reviewed',
            'what_happens': 'We will prepare your items and contact you soon',
            'icon': '📋'
        },
        'Processing': {
            'title': 'Processing',
            'description': 'Your items are being prepared for collection',
            'what_happens': 'We will notify you when your items are ready',
            'icon': '⚙️'
        },
        'Ready for Pickup': {
            'title': 'Ready for Collection',
            'description': 'Your order is ready at your verification centre',
            'what_happens': 'Visit the centre to collect your items',
            'icon': '✅'
        },
        'Shipped': {
            'title': 'On the Way',
            'description': 'Your order has been shipped and is on its way to you',
            'what_happens': 'You will receive your items soon',
            'icon': '🚚'
        },
        'Delivered': {
            'title': 'Collected',
            'description': 'Your order has been collected',
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
    Generate a branded, paginated receipt with separate BXC and NGN summaries.
    
    Args:
        order: Order object
        user: User object
    
    Returns:
        BytesIO object containing PDF data
    """
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=42,
            leftMargin=42,
            topMargin=38,
            bottomMargin=54,
            title=f"Receipt-{order.order_number}",
            author="Barter Express",
        )
        navy = colors.HexColor('#054e97')
        orange = colors.HexColor('#ff7a00')
        ink = colors.HexColor('#182b43')
        muted = colors.HexColor('#61738a')
        pale = colors.HexColor('#f1f6fc')
        line = colors.HexColor('#dce5ef')
        width = doc.width - 12
        elements = []
        styles = getSampleStyleSheet()
        body = ParagraphStyle(
            'ReceiptBody', parent=styles['Normal'], fontSize=9, leading=13,
            textColor=ink, splitLongWords=True,
        )
        small = ParagraphStyle(
            'ReceiptSmall', parent=body, fontSize=8, leading=11, textColor=muted,
        )
        heading = ParagraphStyle(
            'ReceiptHeading', parent=body, fontName='Helvetica-Bold',
            fontSize=11, leading=15, textColor=navy,
            spaceBefore=17, spaceAfter=8, keepWithNext=True,
        )
        white = ParagraphStyle(
            'ReceiptWhite', parent=body, textColor=colors.white,
            fontName='Helvetica-Bold',
        )
        title = ParagraphStyle(
            'ReceiptTitle', parent=body, fontName='Helvetica-Bold',
            fontSize=25, leading=30, textColor=navy, alignment=2,
        )

        def text(value, style=body):
            return Paragraph(escape(str(value if value is not None else 'Not recorded')), style)

        def amount(value, currency='BXC'):
            return f"{value:,.2f} {currency}" if value is not None else 'Not recorded'

        def details(rows):
            table = Table(
                [[text(label, small), text(value)] for label, value in rows],
                colWidths=[width * 0.29, width * 0.71], hAlign='LEFT',
            )
            table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BACKGROUND', (0, 0), (-1, -1), pale),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('LINEBELOW', (0, 0), (-1, -2), 0.4, colors.white),
            ]))
            return table

        def item_table(headers, rows, widths):
            table = Table(
                [[text(label, white) for label in headers]]
                + [[text(value) for value in row] for row in rows],
                colWidths=widths, repeatRows=1, hAlign='LEFT',
            )
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), navy),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, pale]),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('LINEBELOW', (0, 1), (-1, -1), 0.5, line),
            ]))
            return table

        logo = Image(str(Path(__file__).resolve().parent / 'static' / 'logo.png'),
                     width=66, height=66, mask='auto')
        brand = Paragraph(
            '<b>BARTER EXPRESS</b><br/><font size="8" color="#61738a">'
            'Your transaction, clearly recorded.</font>', body,
        )
        header = Table(
            [[logo, brand, Paragraph('RECEIPT', title)]],
            colWidths=[78, width - 238, 160],
            hAlign='LEFT',
        )
        header.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
            ('LINEBELOW', (0, 0), (-1, -1), 3, orange),
        ]))
        elements.extend([header, Spacer(1, 16)])
        elements.append(details([
            ('Order reference', order.order_number),
            ('Order date', order.date_ordered.strftime('%d %B %Y, %H:%M')),
            ('Order status', 'Cancelled' if order.cancelled else order.status),
            ('Customer', user.username),
            ('Email', user.email),
        ]))

        elements.append(Paragraph('01 / ITEMS IN THIS ORDER', heading))
        rows = []
        for order_item in order.items:
            item = order_item.item
            rows.append([
                item.item_number if item else f'Item {order_item.item_id}',
                item.name if item else 'Item no longer available',
                item.condition if item else 'Not recorded',
                amount(order.total_credits if len(order.items) == 1 else item.value)
                if item else 'Not recorded',
            ])
        elements.append(item_table(
            ['Item reference', 'Item description', 'Condition', 'Value (BXC)'],
            rows or [['-', 'No items recorded', '-', '-']],
            [width * 0.21, width * 0.39, width * 0.18, width * 0.22],
        ))

        elements.append(Paragraph('02 / BXC TRANSACTION SUMMARY', heading))
        elements.append(details([
            ('Order value', amount(order.total_credits)),
            ('Balance before order', amount(order.credits_balance_before)),
            ('BXC used', amount(order.credits_used)),
            ('Balance after order', amount(order.credits_balance_after)),
        ]))
        elements.append(Spacer(1, 7))
        elements.append(text(
            'Balances above are the recorded order-time balances, not your current wallet balance. '
            'BXC (Barter Express Credits) and NGN (Nigerian naira) are shown separately.',
            small,
        ))

        reservation = order.reservation
        if reservation:
            funding_elements = [Paragraph('03 / RESERVATION & FUNDING', heading)]
            funding_rows = [
                ('Reservation reference', f'RSV-{reservation.id:06d}'),
                ('Funding method', reservation.funding_mode.replace('_', ' ').title()),
                ('Reservation status', reservation.status.replace('_', ' ').title()),
            ]
            if reservation.completed_at:
                funding_rows.append((
                    'Settlement date', reservation.completed_at.strftime('%d %B %Y, %H:%M'),
                ))
            funding_elements.append(details(funding_rows))
            if reservation.backing_assets:
                funding_elements.append(Spacer(1, 8))
                asset_rows = []
                for asset in reservation.backing_assets:
                    item = asset.item
                    asset_rows.append([
                        item.name if item else f'Item {asset.item_id}',
                        amount(asset.amount),
                        'Excluded' if asset.excluded_from_settlement
                        else asset.verification_status.replace('_', ' ').title(),
                    ])
                funding_elements.append(item_table(
                    ['Backing item', 'Recorded value', 'Verification'],
                    asset_rows, [width * 0.48, width * 0.27, width * 0.25],
                ))
            elements.append(KeepTogether(funding_elements))

        elements.append(Paragraph(
            ('04' if reservation else '03') + ' / COLLECTION & SERVICE FEES', heading,
        ))
        delivery_rows = [('Collection method', 'Verification centre' if order.delivery_method == 'pickup'
                          else 'Retired test booking')]
        if order.delivery_method != 'pickup' and order.delivery_address:
            delivery_rows.append(('Delivery address', order.delivery_address))
        if order.pickup_station:
            station = order.pickup_station
            delivery_rows.append((
                'Verification Station', f'{station.name}, {station.address}, {station.city}, {station.state}',
            ))
        if order.estimated_delivery_date:
            delivery_rows.append((
                'Estimated collection', order.estimated_delivery_date.strftime('%d %B %Y'),
            ))
        if order.actual_delivery_date:
            delivery_rows.append((
                'Collected on', order.actual_delivery_date.strftime('%d %B %Y'),
            ))
        if order.delivery_method != 'pickup' and order.logistics_fee_naira:
            delivery_rows.append(('Historical logistics fee', amount(order.logistics_fee_naira, 'NGN')))
        if reservation and reservation.service_fee_status != 'not_required':
            delivery_rows.extend([
                ('Transaction service fee', amount(reservation.service_fee_naira, 'NGN')),
                ('Service-fee payment status', reservation.service_fee_status.replace('_', ' ').title()),
                ('Final terms accepted', reservation.final_terms_accepted_at.strftime('%d %B %Y, %H:%M UTC')
                 if reservation.final_terms_accepted_at else 'Not accepted'),
            ])
        if reservation and order.delivery_method != 'pickup':
            delivery_rows.append((
                'Fee status', reservation.delivery_fee_status.replace('_', ' ').title(),
            ))
        elements.append(details(delivery_rows))
        if order.delivery_method != 'pickup':
            elements.extend([Spacer(1, 7), text(
                'This retired test booking cannot be fulfilled. Historical charges are '
                'recorded for reconciliation only. Contact support about any payment.', small,
            )])
        if order.cancelled or order.cancellation_reason:
            elements.append(Paragraph('CANCELLATION RECORD', heading))
            cancellation_rows = [('Reason', order.cancellation_reason or 'Not recorded')]
            if order.cancelled_at:
                cancellation_rows.append((
                    'Cancelled on', order.cancelled_at.strftime('%d %B %Y, %H:%M'),
                ))
            elements.append(details(cancellation_rows))
        if order.transaction_notes:
            elements.append(Paragraph('TRANSACTION NOTES', heading))
            elements.append(text(order.transaction_notes))
        elements.extend([Spacer(1, 18), text(
            'Thank you for choosing Barter Express. Keep this receipt for your records and '
            'quote your order reference when contacting support. This receipt records the '
            'order status at download; it does not confirm delivery or an unrecorded payment.',
            small,
        )])

        def page_footer(canvas, document):
            canvas.saveState()
            if document.page > 1:
                canvas.setFillColor(navy)
                canvas.setFont('Helvetica-Bold', 8)
                canvas.drawString(48, letter[1] - 25, 'BARTER EXPRESS / RECEIPT')
                canvas.setFont('Helvetica', 8)
                canvas.drawRightString(letter[0] - 48, letter[1] - 25, order.order_number)
                canvas.setStrokeColor(orange)
                canvas.line(48, letter[1] - 32, letter[0] - 48, letter[1] - 32)
            canvas.setStrokeColor(line)
            canvas.line(48, 40, letter[0] - 48, 40)
            canvas.setFillColor(muted)
            canvas.setFont('Helvetica', 8)
            canvas.drawString(48, 27, f'Barter Express | Generated {datetime.utcnow():%d %b %Y %H:%M} UTC')
            canvas.drawRightString(letter[0] - 48, 27, f'Page {document.page}')
            canvas.restoreState()

        doc.build(elements, onFirstPage=page_footer, onLaterPages=page_footer)
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
                    <h2>🛒 Barter Express Transaction Receipt</h2>
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
                    <p>Thank you for using Barter Express!</p>
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
