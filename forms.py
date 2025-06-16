from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, SelectField, DecimalField, FileField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from flask_wtf.file import FileAllowed
from models import User, Admin

# ------------------ USER FORMS ------------------ #

class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=25)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('Email already registered.')

    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first():
            raise ValidationError('Username already taken.')


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class UploadItemForm(FlaskForm):
    name = StringField('Item Name', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Length(max=500)])
    condition = SelectField('Condition', choices=[('Brand New', 'Brand New'), ('Fairly Used', 'Fairly Used')], validators=[DataRequired()])
    category = SelectField('Category', choices=[
        ("Electronics", "Electronics"),
        ("Fashion / Clothing", "Fashion / Clothing"),
        ("Footwear", "Footwear"),
        ("Home & Kitchen", "Home & Kitchen"),
        ("Beauty & Personal Care", "Beauty & Personal Care"),
        ("Sports & Outdoors", "Sports & Outdoors"),
        ("Groceries", "Groceries"),
        ("Furniture", "Furniture"),
        ("Toys & Games", "Toys & Games"),
        ("Books & Stationery", "Books & Stationery"),
        ("Health & Wellness", "Health & Wellness"),
        ("Automotive", "Automotive")
    ], validators=[DataRequired()])
    image_url = StringField('Image URL')
    submit = SubmitField('Submit Item')


class PasswordResetRequestForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')


# ------------------ ADMIN FORMS ------------------ #

class AdminRegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=25)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register Admin')

    def validate_email(self, email):
        if Admin.query.filter_by(email=email.data).first():
            raise ValidationError('Email already registered.')

    def validate_username(self, username):
        if Admin.query.filter_by(username=username.data).first():
            raise ValidationError('Username already taken.')


class AdminLoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')
