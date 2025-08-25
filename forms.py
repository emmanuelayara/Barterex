from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, SelectField, DecimalField, FileField, IntegerField, MultipleFileField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional
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


class ProfileUpdateForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone_number = StringField('Phone Number', validators=[Length(min=10, max=15)])
    address = TextAreaField('Address', validators=[Length(max=200)])
    city = StringField('City', validators=[Length(max=50)])
    state = StringField('State', validators=[Length(max=50)])
    profile_picture = FileField('Profile Picture', validators=[FileAllowed(['jpg', 'jpeg', 'png'], 'Images only!')])
    submit = SubmitField ('Update Profile')
    


class UploadItemForm(FlaskForm):
    name = StringField('Item Name', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Length(max=500), DataRequired()])
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
    # Changed to support multiple files
    images = MultipleFileField('Upload Images (Max 6)', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])
    submit = SubmitField('Submit Item')


class OrderForm(FlaskForm):
    delivery_method = SelectField("Delivery Method", choices=[
        ("home delivery", "Home Delivery"),
        ("pickup", "Pickup")
    ])
    delivery_address = StringField("Delivery Address", validators=[Optional()])
    pickup_station = SelectField("Pickup Station", choices=[], coerce=int, validators=[Optional()])
    submit = SubmitField("Place Order")


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


class PickupStationForm(FlaskForm):
    name = StringField('Station Name', validators=[DataRequired()])
    address = StringField('Address', validators=[DataRequired()])
    state = StringField('State', validators=[DataRequired()])
    city = StringField('City', validators=[DataRequired()])
    submit = SubmitField('Add Pickup Station')