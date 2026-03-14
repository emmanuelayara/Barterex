from flask import Blueprint, render_template

info_bp = Blueprint('info', __name__, url_prefix='/info')

@info_bp.route('/about')
def about():
    return render_template('info/about.html')

@info_bp.route('/how-it-works')
def how_it_works():
    return render_template('info/how_it_works.html')

@info_bp.route('/safety')
def safety():
    return render_template('info/safety.html')

@info_bp.route('/contact')
def contact_page():
    return render_template('info/contact.html')

@info_bp.route('/faq')
def faq():
    return render_template('info/faq.html')

@info_bp.route('/terms')
def terms():
    return render_template('info/terms.html')

@info_bp.route('/privacy')
def privacy():
    return render_template('info/privacy.html')
