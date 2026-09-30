"""
Tests for valuator_client.py (the Barterex -> valuator connector).

Run from the Barterex project folder:
    python -m pytest tests/test_valuator_client.py -q
No real valuator, database or OpenAI key is needed: a tiny fake valuator
HTTP server is started for the tests, and `app` / `models` are replaced by
small fakes for the background-job tests.
"""
import base64
import io
import json
import os
import sys
import threading
import time
import types
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import valuator_client as vc  # noqa: E402


# ---------------- fake valuator ----------------

class _Handler(BaseHTTPRequestHandler):
    calls = []
    mode = 'ok'

    def log_message(self, *a):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        _Handler.calls.append(('GET', self.path, dict(self.headers), None))
        self._send(200, {'status': 'healthy'})

    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(n) or b'{}')
        _Handler.calls.append(('POST', self.path, dict(self.headers), body))
        if _Handler.mode == 'unauthorized':
            return self._send(401, {'success': False, 'error': 'Invalid API key'})
        if self.path == '/api/valuate':
            return self._send(200, {
                'success': True, 'fair_value': 250000.0,
                'value_range': {'min': 200000, 'max': 300000},
                'confidence_score': 88, 'total_comparables': 12,
                'sources_used': ['jiji'],
                'credits': {'status': 'APPROVED', 'reason': 'ok'},
                'risk_assessment': {'score': 10, 'level': 'LOW', 'flags': []},
                'database': {'saved': True, 'valuation_id': 77},
            })
        if self.path == '/api/verify':
            return self._send(200, {'success': True})
        self._send(404, {'success': False, 'error': 'nope'})


@pytest.fixture()
def fake_server(monkeypatch):
    _Handler.calls = []
    _Handler.mode = 'ok'
    srv = HTTPServer(('127.0.0.1', 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv('VALUATOR_API_URL', f'http://127.0.0.1:{srv.server_port}')
    monkeypatch.setenv('VALUATOR_API_KEY', 'secret-key')
    monkeypatch.delenv('VALUATOR_ENABLED', raising=False)
    yield srv
    srv.shutdown()


# ---------------- pure helpers ----------------

@pytest.mark.parametrize('text,expected', [
    ('2 years', 2.0), ('6 months', 0.5), ('a year', 1.0), ('1.5 yrs', 1.5),
    ('three weeks', round(3 / 52, 2)), ('about 2 years', 2.0),
    ('', None), (None, None), ('a while', None), ('999 years', None),
])
def test_parse_usage_duration(text, expected):
    assert vc.parse_usage_duration(text) == expected


def test_condition_and_category_maps():
    assert vc.map_condition_to_valuator('Brand New') == 'brand_new'
    assert vc.map_condition_to_valuator('Like New') == 'like_new'
    assert vc.map_condition_to_valuator('Fairly Used') == 'good'
    assert vc.map_condition_to_valuator('For Parts') == 'poor'
    assert vc.map_condition_to_valuator(None) == 'good'
    assert vc.map_category_to_valuator('Phones & Gadgets') == 'electronics'
    assert vc.map_category_to_valuator('Fashion & Clothing') is None
    assert vc.map_category_to_valuator(None) is None


def test_account_days_old():
    assert vc.account_days_old(None) == 365
    assert vc.account_days_old(datetime.utcnow() - timedelta(days=10)) == 10


def test_encode_image_shrinks_big_photo(tmp_path):
    from PIL import Image
    p = tmp_path / 'big.jpg'
    Image.new('RGB', (4000, 3000), 'red').save(p, 'JPEG')
    out = base64.b64decode(vc.encode_image_file_to_base64(str(p)))
    assert max(Image.open(io.BytesIO(out)).size) <= vc.MAX_IMAGE_SIDE


def test_encode_image_non_image_falls_back(tmp_path):
    p = tmp_path / 'x.bin'
    p.write_bytes(b'not an image')
    assert base64.b64decode(vc.encode_image_file_to_base64(str(p))) == b'not an image'


def test_extract_fields_success_and_failure():
    ok = vc.extract_item_ai_fields({
        'success': True, 'fair_value': 100.0, 'confidence_score': 72,
        'value_range': {'min': 90, 'max': 110}, 'total_comparables': 5,
        'credits': {'status': 'PENDING_REVIEW', 'reason': 'check'},
        'risk_assessment': {'score': 40, 'level': 'MEDIUM', 'flags': ['a']},
        'sources_used': ['x'], 'database': {'saved': True, 'valuation_id': 5}})
    assert ok['ai_estimated_value'] == 100.0 and ok['ai_confidence'] == 'medium'
    assert ok['verification_status'] == 'flagged_for_review'
    assert ok['valuator_valuation_id'] == 5 and json.loads(ok['ai_risk_flags']) == ['a']

    not_saved = vc.extract_item_ai_fields({'success': True, 'fair_value': 1, 'database': {'saved': False}})
    assert not_saved['valuator_valuation_id'] is None

    bad = vc.extract_item_ai_fields({'success': False, 'error': 'boom'})
    assert bad['verification_status'] == 'valuation_unavailable' and bad['ai_estimated_value'] is None
    assert vc.extract_item_ai_fields(None)['verification_status'] == 'valuation_unavailable'


def test_is_enabled(monkeypatch):
    monkeypatch.delenv('VALUATOR_API_URL', raising=False)
    assert vc.is_enabled() is False
    monkeypatch.setenv('VALUATOR_API_URL', 'http://x')
    assert vc.is_enabled() is True
    monkeypatch.setenv('VALUATOR_ENABLED', 'false')
    assert vc.is_enabled() is False


# ---------------- HTTP against the fake valuator ----------------

def test_valuate_sends_key_and_omits_unknowns(fake_server):
    r = vc.ValuatorClient().valuate(title='iPhone 12', condition='good', age_years=None, category=None)
    assert r['success'] and r['fair_value'] == 250000.0
    _, path, headers, body = _Handler.calls[-1]
    assert path == '/api/valuate'
    assert headers.get('Authorization') == 'Bearer secret-key'
    assert 'age_years' not in body and 'category' not in body


def test_valuate_sends_age_zero_and_category(fake_server):
    vc.ValuatorClient().valuate(title='x', age_years=0, category='electronics')
    body = _Handler.calls[-1][3]
    assert body['age_years'] == 0 and body['category'] == 'electronics'


def test_wrong_key_returns_error_not_exception(fake_server):
    _Handler.mode = 'unauthorized'
    r = vc.ValuatorClient().valuate(title='x')
    assert r['success'] is False and r.get('error')


def test_valuator_down_returns_error_not_exception(monkeypatch):
    monkeypatch.setenv('VALUATOR_API_URL', 'http://127.0.0.1:1')
    r = vc.ValuatorClient().valuate(title='x')
    assert r['success'] is False
    assert vc.ValuatorClient().is_available() is False


def test_health(fake_server):
    assert vc.ValuatorClient().is_available() is True


def test_verify_payload(fake_server):
    r = vc.ValuatorClient().verify(77, 'passed', 'admin-1', verified_value=250000, verified_condition='good')
    assert r['success']
    body = _Handler.calls[-1][3]
    assert body == {'valuation_id': 77, 'status': 'passed', 'verifier_id': 'admin-1',
                    'verified_value': 250000, 'verified_condition': 'good'}


# ---------------- background jobs with fake app / models ----------------

class FakeItem:
    def __init__(self, **kw):
        self.id = 1
        self.valuator_valuation_id = None
        self.status = 'pending'
        self.value = None
        self.rejection_reason = None
        self.condition = 'Fairly Used'
        self.__dict__.update(kw)


@pytest.fixture()
def fake_app(monkeypatch):
    store = {'item': FakeItem(), 'commits': 0}

    class Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class Session:
        def get(self, model, pk): return store['item']
        def commit(self): store['commits'] += 1
        def rollback(self): pass

    app_mod = types.ModuleType('app')
    app_mod.app = types.SimpleNamespace(app_context=lambda: Ctx())
    app_mod.db = types.SimpleNamespace(session=Session())
    models_mod = types.ModuleType('models')
    models_mod.Item = FakeItem
    monkeypatch.setitem(sys.modules, 'app', app_mod)
    monkeypatch.setitem(sys.modules, 'models', models_mod)
    return store


def test_valuation_job_fills_item(fake_server, fake_app, tmp_path):
    from PIL import Image
    Image.new('RGB', (50, 50), 'blue').save(tmp_path / 'a.jpg', 'JPEG')
    job = {'item_id': 1, 'title': 'iPhone', 'description': 'nice', 'condition': 'good',
           'sale_type': 'second_hand', 'age_years': 2.0, 'category': 'electronics',
           'image_paths': [str(tmp_path / 'a.jpg'), str(tmp_path / 'missing.jpg')],
           'account_days': 30}
    vc._run_valuation_job(job)
    item = fake_app['item']
    assert item.ai_estimated_value == 250000.0
    assert item.valuator_valuation_id == 77
    assert item.verification_status == 'ai_approved'
    assert item.ai_valuated_at is not None and fake_app['commits'] == 1
    body = _Handler.calls[-1][3]
    assert len(body['images']) == 1 and body['image_count'] == 2   # missing photo skipped, not fatal


def test_valuation_job_valuator_down_marks_unavailable(monkeypatch, fake_app):
    monkeypatch.setenv('VALUATOR_API_URL', 'http://127.0.0.1:1')
    vc._run_valuation_job({'item_id': 1, 'title': 't', 'description': '', 'condition': 'good',
                           'sale_type': 'second_hand', 'age_years': None, 'category': None,
                           'image_paths': [], 'account_days': 1})
    item = fake_app['item']
    assert item.verification_status == 'valuation_unavailable'
    assert item.ai_valuated_at is not None


def test_verification_job_reports_only_real_outcome(fake_server, fake_app):
    item = fake_app['item']
    item.valuator_valuation_id = 77
    item.status, item.value = 'approved', 250000.0
    vc._run_verification_job(1, 'passed', 'admin-1', 0)
    assert _Handler.calls[-1][1] == '/api/verify'
    assert _Handler.calls[-1][3]['status'] == 'passed'

    n = len(_Handler.calls)
    vc._run_verification_job(1, 'failed', 'admin-1', 0)      # item is approved, so 'failed' is not true
    assert len(_Handler.calls) == n


def test_verification_skipped_without_valuation_id(fake_server, fake_app):
    fake_app['item'].status = 'approved'
    vc._run_verification_job(1, 'passed', 'admin-1', 0)
    assert _Handler.calls == []


def test_start_and_report_do_nothing_when_disabled(monkeypatch):
    monkeypatch.delenv('VALUATOR_API_URL', raising=False)
    assert vc.start_ai_valuation(object(), object(), '/tmp') is False
    assert vc.report_verification(1, 'passed', 1) is False


def test_start_never_raises_on_bad_item(monkeypatch):
    monkeypatch.setenv('VALUATOR_API_URL', 'http://127.0.0.1:1')
    assert vc.start_ai_valuation(None, None, '/tmp') is False


def test_build_valuation_job(monkeypatch):
    img = types.SimpleNamespace(image_url='b.jpg', order_index=2)
    img0 = types.SimpleNamespace(image_url='a.jpg', order_index=1)
    item = types.SimpleNamespace(id=9, name='Laptop', description='HP', condition='Brand New',
                                 usage_duration='', category='Phones & Gadgets', images=[img, img0])
    user = types.SimpleNamespace(created_at=datetime.utcnow() - timedelta(days=5))
    job = vc.build_valuation_job(item, user, '/up')
    assert job['sale_type'] == 'new' and job['category'] == 'electronics'
    assert job['age_years'] is None and job['account_days'] == 5
    assert [os.path.basename(p) for p in job['image_paths']] == ['a.jpg', 'b.jpg']
