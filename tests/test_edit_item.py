import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

from PIL import Image
from sqlalchemy.exc import SQLAlchemyError

from app import app, db, limiter
from models import Item, ItemImage, ItemVideo, User


class EditItemTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        self.previous_limiter = limiter.enabled
        limiter.enabled = False
        db.create_all()
        self.user = User(username='edit-owner', email='edit@example.com', password_hash='test')
        db.session.add(self.user)
        db.session.flush()
        self.old_valuation_at = datetime.utcnow() - timedelta(days=31)
        self.item = Item(
            name='Original phone', description='Original description of this test phone.',
            user_id=self.user.id, uploaded_by_id=self.user.id, category='Phones & Gadgets',
            condition='Fairly Used', usage_duration='6 months', status='valuation_only',
            image_url='original.jpg', ai_estimated_value=500, ai_valuated_at=self.old_valuation_at,
        )
        self.item.images.append(ItemImage(image_url='original.jpg', is_primary=True, order_index=0))
        db.session.add(self.item)
        db.session.commit()
        self.item_id = self.item.id
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.user.id)
            session['_fresh'] = True
        self.fields = {
            'name': 'Updated phone', 'description': 'Updated description of this test phone.',
            'condition': 'Brand New', 'category': 'Phones & Gadgets', 'usage_duration': '',
        }
        self.folder = tempfile.TemporaryDirectory()
        self.config_patch = patch.dict(app.config, {'UPLOAD_FOLDER': self.folder.name})
        self.config_patch.start()
        self.analysis_patch = patch('image_analyzer.analyze_image_url', return_value={})
        self.analysis_patch.start()

    def tearDown(self):
        self.analysis_patch.stop()
        self.config_patch.stop()
        self.folder.cleanup()
        limiter.enabled = self.previous_limiter
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def photos(self, count=6, color='blue'):
        photos = []
        for index in range(count):
            image = io.BytesIO()
            Image.new('RGB', (30, 30), color).save(image, 'JPEG')
            image.seek(0)
            photos.append((image, f'camera-{index}.jpg'))
        return photos

    def preview(self, **overrides):
        fields = {**self.fields, 'edit_item_id': str(self.item_id), **overrides}
        with patch('valuator_client.is_enabled', return_value=True), \
             patch('valuator_client.client.valuate', return_value={
                 'success': True, 'fair_value': 750, 'confidence_score': 90,
                 'value_range': {'min': 700, 'max': 800}, 'credits': {'status': 'approved'},
             }) as valuate:
            response = self.client.post('/items/estimate-value', data={**fields, 'images': self.photos()})
        self.assertEqual(response.status_code, 200)
        valuate.assert_called_once()
        return response.get_json()['token']

    def save(self, token=None, **overrides):
        fields = {**self.fields, 'images': self.photos(), **overrides}
        if token:
            fields['ai_valuation_token'] = token
        return self.client.post(
            f'/upload?edit={self.item_id}', data=fields,
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )

    def assert_original(self):
        db.session.refresh(self.item)
        self.assertEqual(self.item.name, 'Original phone')
        self.assertEqual(self.item.description, 'Original description of this test phone.')
        self.assertEqual(self.item.image_url, 'original.jpg')
        self.assertEqual([image.image_url for image in self.item.images], ['original.jpg'])
        self.assertEqual(self.item.ai_estimated_value, 500)
        self.assertEqual(self.item.ai_valuated_at, self.old_valuation_at)
        self.assertEqual(Item.query.count(), 1)

    def test_edit_opens_prefilled_camera_upload_form(self):
        response = self.client.get(f'/edit/{self.item_id}')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f'/upload?edit={self.item_id}')
        response = self.client.get(response.location)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Edit Your Item', html)
        self.assertIn('value="Original phone"', html)
        self.assertIn('Original description of this test phone.', html)
        self.assertIn('value="6 months"', html)
        self.assertIn('selected value="Fairly Used"', html)
        self.assertIn('selected value="Phones &amp; Gadgets"', html)
        self.assertIn(f'data-edit-item-id="{self.item_id}"', html)
        self.assertIn('Revalue &amp; save changes', html)
        self.assertNotIn('type="file"', html)
        self.assertNotIn('deviceCameraInput', html)
        self.assertIn('id="photoFocusBtn"', html)
        self.assertIn('Open In-Page Camera', html)
        self.assertIn('id="aiValuationManual" hidden', html)
        self.assertIn('id="aiValuationSubmitAnyway" hidden', html)
        self.assertIn('6-15 new camera photos', html)

    def test_successful_edit_revalues_same_item_and_replaces_photos_without_credits(self):
        token = self.preview()
        credits = self.user.credits
        with patch('routes.items.start_ai_valuation') as background:
            response = self.save(token)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        self.assertEqual(response.get_json()['redirect_url'], '/my_valuations')
        db.session.refresh(self.item)
        self.assertEqual(Item.query.count(), 1)
        self.assertEqual(self.item.id, self.item_id)
        self.assertEqual(self.item.name, 'Updated phone')
        self.assertEqual(self.item.ai_estimated_value, 750)
        self.assertIsNone(self.item.usage_duration)
        self.assertGreater(self.item.ai_valuated_at, self.old_valuation_at)
        self.assertFalse(self.item.valuation_is_expired())
        self.assertEqual(self.item.valuation_expires_at, self.item.ai_valuated_at + timedelta(days=30))
        self.assertEqual(len(self.item.images), 6)
        self.assertNotEqual(self.item.image_url, 'original.jpg')
        self.assertEqual(self.item.status, 'valuation_only')
        self.assertFalse(self.item.credited)
        self.assertEqual(self.user.credits, credits)
        self.assertEqual(ItemVideo.query.count(), 0)
        background.assert_not_called()
        with self.client.session_transaction() as session:
            self.assertNotIn('pending_item_valuation', session)
        self.assertIn('Updated phone', self.client.get('/my_valuations').get_data(as_text=True))

    def test_save_without_fresh_preview_preserves_original(self):
        response = self.save()
        self.assertEqual(response.status_code, 400)
        self.assertIn('fresh AI valuation', response.get_json()['error'])
        self.assert_original()
        self.assertEqual(os.listdir(self.folder.name), [])

    def test_changed_details_or_photos_cannot_reuse_preview(self):
        for changes in ({'name': 'Different phone'}, {'images': self.photos(color='red')}):
            with self.subTest(changes=list(changes)):
                response = self.save(self.preview(), **changes)
                self.assertEqual(response.status_code, 400)
                self.assert_original()

    def test_wrong_item_and_new_upload_preview_cannot_be_used(self):
        for target in (None, self.item_id + 1):
            with self.subTest(target=target):
                token = self.preview()
                with self.client.session_transaction() as session:
                    pending = session['pending_item_valuation']
                    pending['edit_item_id'] = target
                    session['pending_item_valuation'] = pending
                self.assertEqual(self.save(token).status_code, 400)
                self.assert_original()

    def test_expired_preview_is_rejected(self):
        token = self.preview()
        with self.client.session_transaction() as session:
            pending = session['pending_item_valuation']
            pending['expires_at'] = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
            session['pending_item_valuation'] = pending
        self.assertEqual(self.save(token).status_code, 400)
        self.assert_original()

    def test_preview_cannot_overwrite_a_more_recent_edit(self):
        token = self.preview()
        newer = datetime.utcnow()
        self.item.ai_valuated_at = newer
        self.item.ai_estimated_value = 900
        db.session.commit()
        self.assertEqual(self.save(token).status_code, 400)
        db.session.refresh(self.item)
        self.assertEqual(self.item.ai_estimated_value, 900)
        self.assertEqual(self.item.ai_valuated_at, newer)

    def test_ai_failure_preserves_original_and_no_manual_fallback(self):
        with patch('valuator_client.is_enabled', return_value=True), \
             patch('valuator_client.client.valuate', return_value={'success': False, 'error': 'Unavailable'}):
            response = self.client.post('/items/estimate-value', data={
                **self.fields, 'edit_item_id': str(self.item_id), 'images': self.photos(),
            })
        self.assertEqual(response.status_code, 502)
        self.assert_original()
        self.assertEqual(self.save(manual_review='1').status_code, 400)
        self.assert_original()

    def test_edit_requires_new_photos_with_six_to_fifteen_count(self):
        for count in (0, 5, 16):
            with self.subTest(count=count):
                self.assertEqual(self.save(images=self.photos(count)).status_code, 400)
                with patch('valuator_client.client.valuate') as valuate:
                    response = self.client.post('/items/estimate-value', data={
                        **self.fields, 'edit_item_id': str(self.item_id), 'images': self.photos(count),
                    })
                self.assertEqual(response.status_code, 400)
                valuate.assert_not_called()
                self.assert_original()

    def test_edit_accepts_fifteen_new_photos(self):
        with patch('valuator_client.is_enabled', return_value=True), \
             patch('valuator_client.client.valuate', return_value={'success': True, 'fair_value': 800}):
            preview = self.client.post('/items/estimate-value', data={
                **self.fields, 'edit_item_id': str(self.item_id), 'images': self.photos(15),
            })
        self.assertEqual(preview.status_code, 200)
        response = self.save(preview.get_json()['token'], images=self.photos(15))
        self.assertEqual(response.status_code, 200)
        db.session.refresh(self.item)
        self.assertEqual(len(self.item.images), 15)
        self.assertEqual(self.item.ai_estimated_value, 800)

    def test_legacy_post_cannot_bypass_new_preview_and_photo_rules(self):
        response = self.client.post(f'/edit/{self.item_id}', data=self.fields, follow_redirects=True)
        self.assertEqual(response.status_code, 400)
        self.assert_original()

    def test_commit_failure_rolls_back_item_and_removes_new_files(self):
        token = self.preview()
        with patch.object(db.session, 'commit', side_effect=SQLAlchemyError('Test commit failure')):
            response = self.save(token)
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.get_json()['success'])
        self.assert_original()
        self.assertEqual(os.listdir(self.folder.name), [])

    def test_failed_image_processing_rolls_back_and_cleans_partial_files(self):
        from file_upload_validator import optimize_image_for_storage
        calls = 0

        def fail_second(data, extension):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('Test image failure')
            return optimize_image_for_storage(data, extension)

        token = self.preview()
        with patch('routes.items.optimize_image_for_storage', side_effect=fail_second):
            response = self.save(token)
        self.assertEqual(response.status_code, 400)
        self.assert_original()
        self.assertEqual(os.listdir(self.folder.name), [])

    def test_submitted_review_approved_and_locked_items_cannot_be_edited(self):
        for status in ('manual_review_pending', 'pending_activation', 'approved', 'rejected'):
            with self.subTest(status=status):
                self.item.status = status
                db.session.commit()
                response = self.client.get(f'/edit/{self.item_id}')
                self.assertEqual(response.status_code, 302)
                self.assertNotIn('/upload', response.location)
                self.assertEqual(self.save().status_code, 409)
        self.item.status = 'valuation_only'
        db.session.add(ItemVideo(
            item_id=self.item_id, uploaded_by_id=self.user.id,
            temp_video_url='rejected-video', status='rejected',
        ))
        db.session.commit()
        self.assertEqual(self.save().status_code, 409)

    def test_other_users_item_cannot_be_edited_or_revalued(self):
        other = User(username='other-owner', email='other-edit@example.com', password_hash='test')
        db.session.add(other)
        db.session.flush()
        self.item.user_id = other.id
        db.session.commit()
        self.assertEqual(self.client.get(f'/edit/{self.item_id}').status_code, 404)
        self.assertEqual(self.client.get(f'/upload?edit={self.item_id}').status_code, 404)
        with patch('valuator_client.client.valuate') as valuate:
            response = self.client.post('/items/estimate-value', data={
                **self.fields, 'edit_item_id': str(self.item_id), 'images': self.photos(),
            })
        self.assertEqual(response.status_code, 404)
        valuate.assert_not_called()
