import os
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from datetime import datetime
from flask_mail import Mail, Message

app = Flask(__name__)

UPLOAD_FOLDER = 'static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # Max size: 2MB

app.config['SECRET_KEY'] = 'ORdt0qCDzsPf5jDFgQNFQeAZRQrro7nq'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///barter.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ✅ Mail config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'info.barterex@gmail.com'       # change this
app.config['MAIL_PASSWORD'] = 'cjctyrdszqxyippm'           # app password (not Gmail login)
app.config['MAIL_DEFAULT_SENDER'] = ('Barter Express (Barterex)', 'info.barterex@gmail.com')

# ✅ Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)
mail = Mail(app)

# Import routes and models
from routes import *
from models import *

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()
