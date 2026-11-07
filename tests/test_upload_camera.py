import io
import os
import tempfile
import unittest
from html.parser import HTMLParser
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from PIL import Image
from app import app, db, limiter
from models import Item, User


class FormElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class UploadCameraTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        if limiter:
            self.previous_limiter = limiter.enabled
            limiter.enabled = False
        db.drop_all()
        db.create_all()
        user = User(username='camera-user', email='camera@example.com', password_hash='test',
                    phone_number='12345', address='Office', city='Lagos', state='Lagos',
                    id_verification_status='submitted')
        db.session.add(user)
        db.session.commit()
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user.id)
            session['_fresh'] = True

    def tearDown(self):
        if limiter:
            limiter.enabled = self.previous_limiter
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_upload_form_offers_camera_not_file_picker(self):
        response = self.client.get('/upload')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        parser = FormElements()
        parser.feed(html)
        self.assertFalse(any(tag == 'input' and attrs.get('type') == 'file'
                             for tag, attrs in parser.elements))
        elements = {attrs['id']: (tag, attrs) for tag, attrs in parser.elements if 'id' in attrs}
        self.assertIn('no-loading', elements['uploadForm'][1]['class'])
        self.assertEqual(elements['fileUploadArea'][0], 'button')
        self.assertEqual(elements['capturePhotoBtn'][0], 'button')
        self.assertIn('disabled', elements['capturePhotoBtn'][1])
        self.assertEqual(elements['cameraPreview'][0], 'video')
        self.assertIn('playsinline', elements['cameraPreview'][1])
        self.assertIn('muted', elements['cameraPreview'][1])
        self.assertIn('Gallery uploads are not allowed.', html)
        self.assertNotIn('handleMultipleFileUpload', html)
        self.assertNotIn('dataTransfer.files', html)
        self.assertIn('Submit for manual review instead', html)

    def test_camera_jpegs_use_existing_upload_validation(self):
        def photo(index):
            data = io.BytesIO()
            Image.new('RGB', (30, 30), 'blue').save(data, 'JPEG')
            data.seek(0)
            return data, f'item-camera-{index}.jpg'

        fields = {
            'name': 'Camera test item', 'description': 'A detailed description of this camera test item.',
            'category': 'Phones & Gadgets', 'condition': 'Brand New', 'manual_review': '1',
        }
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(app.config, {'UPLOAD_FOLDER': folder}), \
             patch('routes.items.notify_admins'), \
             patch('image_analyzer.analyze_image_url', return_value={}):
            response = self.client.post('/upload', data={
                **fields, 'images': [photo(i) for i in range(5)],
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(Item.query.count(), 0)
            response = self.client.post('/upload', data={
                **fields, 'images': [photo(i) for i in range(6)],
            })
            self.assertEqual(response.status_code, 302)
            uploaded = Item.query.one()
            self.assertEqual(len(uploaded.images), 6)
            self.assertEqual(uploaded.status, 'manual_review_pending')
