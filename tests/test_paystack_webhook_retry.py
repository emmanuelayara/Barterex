"""Webhook retries use mocked Paystack responses, never live payment credentials."""
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

REFERENCE = 'offline-webhook-retry-reference'
SECRET = 'offline-webhook-signature-key'
ENDPOINT = '/payments/webhook'


@pytest.fixture
def webhook_context(monkeypatch):
    from app import app, db
    import paystack_payment_service as module
    service = module.PaystackPaymentService
    monkeypatch.setitem(app.config, 'TESTING', True)
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    monkeypatch.setattr(service, 'SECRET_KEY', SECRET)
    monkeypatch.setattr(service, 'BASE_URL', 'https://paystack.offline.invalid')
    monkeypatch.setattr(service, 'TEST_MODE', False)
    with app.app_context():
        # Request hooks also query settings; every case needs a complete test schema.
        assert all(engine.url.get_backend_name() == 'sqlite'
                   and engine.url.database in (None, '', ':memory:')
                   for engine in db.engines.values()), 'Tests require in-memory SQLite'
        db.create_all()
        try:
            with app.test_client() as client:
                yield SimpleNamespace(client=client, service=service, module=module)
        finally:
            db.session.remove()
            db.drop_all()
            db.session.remove()


def send_event(context, event='charge.success', signature='valid'):
    raw = json.dumps({'event': event, 'data': {'reference': REFERENCE}},
                     separators=(',', ':')).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if signature == 'valid':
        headers['x-paystack-signature'] = hmac.new(
            SECRET.encode('utf-8'), raw, hashlib.sha512).hexdigest()
    elif signature == 'invalid':
        headers['x-paystack-signature'] = '0' * 128
    return context.client.post(ENDPOINT, data=raw, headers=headers)


def test_signed_failed_verification_is_retryable(webhook_context, monkeypatch):
    verify = Mock(return_value={'success': False, 'error': 'Temporary verification failure'})
    monkeypatch.setattr(webhook_context.service, 'verify_payment', verify)
    response = send_event(webhook_context)
    verify.assert_called_once_with(REFERENCE)
    assert response.status_code == 503
    assert response.get_json()['success'] is False


@pytest.mark.parametrize('failure', [
    {'success': False, 'error': 'Failed to verify payment', 'status_code': 503},
    {'success': False, 'error': 'Payment is already being processed. Check its status.'},
    {'success': False, 'error': 'Payment record not found'},
    {'success': False, 'status': 'pending', 'error': 'Payment is pending'},
])
def test_uncompleted_verification_is_not_acknowledged(webhook_context, monkeypatch, failure):
    monkeypatch.setattr(webhook_context.service, 'verify_payment', Mock(return_value=failure))
    response = send_event(webhook_context)
    assert response.status_code == 503
    assert response.get_json()['success'] is False


@pytest.mark.parametrize('credits', [100, 0])
def test_success_and_already_completed_payments_are_acknowledged(webhook_context, monkeypatch, credits):
    result = {'success': True, 'credits_added': credits, 'new_balance': 500}
    verify = Mock(return_value=result)
    monkeypatch.setattr(webhook_context.service, 'verify_payment', verify)
    response = send_event(webhook_context)
    assert response.status_code == 200
    assert response.get_json() == {'success': True, 'result': result}
    verify.assert_called_once_with(REFERENCE)


def test_retry_can_succeed_after_initial_failure(webhook_context, monkeypatch):
    verify = Mock(side_effect=[
        {'success': False, 'error': 'Temporary failure'},
        {'success': True, 'credits_added': 100, 'new_balance': 500},
    ])
    monkeypatch.setattr(webhook_context.service, 'verify_payment', verify)
    assert send_event(webhook_context).status_code == 503
    assert send_event(webhook_context).status_code == 200
    assert verify.call_count == 2


@pytest.mark.parametrize('signature', ['missing', 'invalid'])
def test_invalid_signatures_never_verify_a_payment(webhook_context, monkeypatch, signature):
    verify = Mock()
    monkeypatch.setattr(webhook_context.service, 'verify_payment', verify)
    assert send_event(webhook_context, signature=signature).status_code == 401
    verify.assert_not_called()


def test_authenticated_unhandled_event_is_acknowledged(webhook_context, monkeypatch):
    verify = Mock()
    monkeypatch.setattr(webhook_context.service, 'verify_payment', verify)
    assert send_event(webhook_context, event='setup.check').status_code == 200
    verify.assert_not_called()


def test_callback_without_reference_keeps_validation_error(webhook_context, monkeypatch):
    verify = Mock()
    monkeypatch.setattr(webhook_context.service, 'verify_payment', verify)
    assert webhook_context.client.get(ENDPOINT).status_code == 400
    verify.assert_not_called()


def test_callback_keeps_existing_failure_page(webhook_context, monkeypatch):
    verify = Mock(return_value={'success': False, 'error': 'Payment is pending'})
    monkeypatch.setattr(webhook_context.service, 'verify_payment', verify)
    response = webhook_context.client.get(ENDPOINT, query_string={'reference': REFERENCE})
    assert response.status_code == 200
    assert response.mimetype == 'text/html'
    verify.assert_called_once_with(REFERENCE)


def prepare_real_verifier(context, monkeypatch):
    payment = SimpleNamespace(id=999, status='pending', user_id=999, amount_naira=100)
    query = Mock()
    query.filter_by.return_value.first.return_value = payment
    monkeypatch.setattr(context.module, 'Payment', SimpleNamespace(query=query))
    rollback = Mock()
    monkeypatch.setattr(context.module.db.session, 'rollback', rollback)
    claim = Mock(side_effect=AssertionError('Unverified payment must not be claimed'))
    monkeypatch.setattr(context.service, '_claim_payment', claim)
    return rollback, claim


def test_actual_verifier_timeout_leaves_webhook_retryable(webhook_context, monkeypatch):
    rollback, claim = prepare_real_verifier(webhook_context, monkeypatch)
    upstream = Mock(side_effect=requests.exceptions.Timeout('offline timeout'))
    monkeypatch.setattr(webhook_context.module.requests, 'get', upstream)
    response = send_event(webhook_context)
    assert response.status_code == 503
    assert response.get_json()['success'] is False
    upstream.assert_called_once()
    rollback.assert_called_once()
    claim.assert_not_called()


@pytest.mark.parametrize('mismatch', [
    {'amount': 9999}, {'currency': 'USD'}, {'reference': 'different-reference'},
])
def test_actual_verifier_rejects_mismatch_without_claiming(webhook_context, monkeypatch, mismatch):
    _, claim = prepare_real_verifier(webhook_context, monkeypatch)
    data = {'status': 'success', 'reference': REFERENCE, 'amount': 10000, 'currency': 'NGN'}
    data.update(mismatch)
    upstream = Mock(return_value=SimpleNamespace(
        status_code=200, json=lambda: {'status': True, 'data': data}))
    monkeypatch.setattr(webhook_context.module.requests, 'get', upstream)
    assert send_event(webhook_context).status_code == 503
    upstream.assert_called_once()
    claim.assert_not_called()
