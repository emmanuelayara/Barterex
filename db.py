"""
Database initialization module
Separates db initialization from app to avoid circular imports
"""
from flask_sqlalchemy import SQLAlchemy

# Create db instance without app binding
db = SQLAlchemy()
