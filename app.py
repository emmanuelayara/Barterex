import os
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate


app = Flask(__name__)


UPLOAD_FOLDER = 'static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # Max size: 2MB

app.config['SECRET_KEY'] = 'super-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///barter.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


# os.environ.get('DATABASE_URL')
#'sqlite:///barter.db'
# postgresql://barter_n7gd_user:txVmlNLLM5YFzI1bkCc28ixYSWTCfcKQ@dpg-d248b2ffte5s73ar0ba0-a.oregon-postgres.render.com/barter_n7gd

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

migrate = Migrate(app, db)

from routes import *
from models import *

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()