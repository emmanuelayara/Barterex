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
    referral_code = StringField('Referral Code (Optional)', validators=[Optional(), Length(max=20)])
    submit = SubmitField('Register')

    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('Email already registered.')

    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first():
            raise ValidationError('Username already taken.')
    
    def validate_referral_code(self, referral_code):
        if referral_code.data:  # Only validate if provided
            from models import User
            referrer = User.query.filter_by(referral_code=referral_code.data).first()
            if not referrer:
                raise ValidationError('Invalid referral code.')


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class ProfileUpdateForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone_number = StringField('Phone Number', validators=[Length(min=10, max=15)])
    address = TextAreaField('Address', validators=[Length(max=200)])
    city = StringField('City', validators=[Length(max=50)])
    state = SelectField('State', choices=[
        ('', 'Select State'),  # Default empty option
        ('Abia', 'Abia'),
        ('Adamawa', 'Adamawa'),
        ('Akwa Ibom', 'Akwa Ibom'),
        ('Anambra', 'Anambra'),
        ('Bauchi', 'Bauchi'),
        ('Bayelsa', 'Bayelsa'),
        ('Benue', 'Benue'),
        ('Borno', 'Borno'),
        ('Cross River', 'Cross River'),
        ('Delta', 'Delta'),
        ('Ebonyi', 'Ebonyi'),
        ('Edo', 'Edo'),
        ('Ekiti', 'Ekiti'),
        ('Enugu', 'Enugu'),
        ('FCT', 'Federal Capital Territory (Abuja)'),
        ('Gombe', 'Gombe'),
        ('Imo', 'Imo'),
        ('Jigawa', 'Jigawa'),
        ('Kaduna', 'Kaduna'),
        ('Kano', 'Kano'),
        ('Katsina', 'Katsina'),
        ('Kebbi', 'Kebbi'),
        ('Kogi', 'Kogi'),
        ('Kwara', 'Kwara'),
        ('Lagos', 'Lagos'),
        ('Nasarawa', 'Nasarawa'),
        ('Niger', 'Niger'),
        ('Ogun', 'Ogun'),
        ('Ondo', 'Ondo'),
        ('Osun', 'Osun'),
        ('Oyo', 'Oyo'),
        ('Plateau', 'Plateau'),
        ('Rivers', 'Rivers'),
        ('Sokoto', 'Sokoto'),
        ('Taraba', 'Taraba'),
        ('Yobe', 'Yobe'),
        ('Zamfara', 'Zamfara')
    ], validators=[DataRequired()])
    profile_picture = FileField('Profile Picture', validators=[FileAllowed(['jpg', 'jpeg', 'png'], 'Images only!')])
    submit = SubmitField('Update Profile')
    


class UploadItemForm(FlaskForm):
    name = StringField('Item Name', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Length(max=2000), DataRequired()])
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
        ("Automotive", "Automotive"), 
        ("Phones & Gadgets", "Phones & Gadgets")
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


class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Reset Password')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Update Password')


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


# ==================== ACCOUNT MANAGEMENT FORMS ==================== #

class ChangePasswordForm(FlaskForm):
    """Form for users to change their password"""
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('new_password', message='Passwords must match')])
    submit = SubmitField('Change Password')


class SecuritySettingsForm(FlaskForm):
    """Form for security preferences"""
    alert_on_new_device = BooleanField('Alert me when login from new device')
    alert_on_location_change = BooleanField('Alert me on location change')
    password_strength_required = SelectField('Required Password Strength', choices=[
        ('weak', 'Weak (6+ characters)'),
        ('medium', 'Medium (8+ chars, numbers, symbols)'),
        ('strong', 'Strong (12+ chars, numbers, symbols, uppercase)')
    ])
    submit = SubmitField('Save Security Settings')


class TwoFactorSetupForm(FlaskForm):
    """Form for enabling 2FA"""
    verification_code = StringField('Verification Code', validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField('Enable 2FA')


class ExportDataForm(FlaskForm):
    """Form for GDPR data export request"""
    confirm = BooleanField('I confirm I want to export my data', validators=[DataRequired()])
    submit = SubmitField('Request Data Export')


class DeleteAccountForm(FlaskForm):
    """Form for account deletion"""
    confirm_delete = BooleanField('I understand this cannot be undone', validators=[DataRequired()])
    confirm_username = StringField('Type your username to confirm', validators=[DataRequired()])
    submit = SubmitField('Delete My Account')