"""Bound the new in-memory handoff without losing photos or the saved-file fallback."""
import base64
from concurrent.futures import ThreadPoolExecutor
import gc
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from services import guest_valuation_service as guests


@pytest.fixture
def guest():
    path = Path(__file__).resolve().parent / 'test_guest_valuation.py'
    spec = importlib.util.spec_from_file_location('guest_handoff_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = module.GuestValuationTests('runTest')
    case.setUp()
    try:
        yield case, module
    finally:
        case.tearDown()


def test_all_fifteen_handoff_photos_keep_order_and_release_before_api(guest):
    case, module = guest
    jobs = []
    before = guests._photo_memory_used
    def result(**kwargs):
        assert guests._photo_memory_used == before
        return module.AI_RESPONSE
    case.valuate.side_effect = result
    with patch('valuator_client.queue_valuator_task', lambda fn, *args: jobs.append(args) or True), \
            patch('valuator_client.encode_image_file_to_base64', side_effect=AssertionError('unexpected disk read')):
        assert case.submit(photos=15).status_code == 200
        record_id, batch = jobs.pop()
        expected = [module.jpeg(i)[0].getvalue() for i in range(15)]
        assert list(batch) == expected
        assert guests._photo_memory_used == before + sum(map(len, expected))
        guests.run_valuation(record_id, batch)
    assert batch == [] and guests._photo_memory_used == before
    assert case.record().status == 'ready'
    assert case.valuate.call_args.kwargs['image_count'] == 15
    assert [base64.b64decode(x) for x in case.valuate.call_args.kwargs['images']] == expected
    folder = Path(guests.record_dir(record_id))
    assert [(folder / n).read_bytes() for n in case.record().image_file_list()] == expected


def test_full_budget_uses_all_fifteen_saved_photos(guest):
    case, module = guest
    from valuator_client import encode_image_file_to_base64
    jobs = []
    with patch.object(guests, 'PHOTO_MEMORY_BUDGET', 0), \
            patch('valuator_client.queue_valuator_task', lambda fn, *args: jobs.append(args) or True), \
            patch('valuator_client.encode_image_file_to_base64', wraps=encode_image_file_to_base64) as read:
        assert case.submit(photos=15).status_code == 200
        record_id, batch = jobs.pop()
        assert batch is None
        guests.run_valuation(record_id, batch)
        assert read.call_count == 15
    assert case.record().status == 'ready'
    assert case.valuate.call_args.kwargs['image_count'] == 15
    assert len(case.valuate.call_args.kwargs['images']) == 15


def test_waiting_jobs_share_budget_and_busy_upload_keeps_disk_fallback(guest):
    case, module = guest
    jobs = []
    size = sum(len(module.jpeg(i)[0].getvalue()) for i in range(6))
    before = guests._photo_memory_used
    with patch.object(guests, 'PHOTO_MEMORY_BUDGET', before + size), \
            patch('valuator_client.queue_valuator_task', lambda fn, *args: jobs.append(args) or True):
        assert case.submit().status_code == 200
        assert case.submit(client=module.app.test_client()).status_code == 200
        assert jobs[0][1] is not None and jobs[1][1] is None
        assert guests._photo_memory_used == before + size
        for record_id, batch in jobs:
            guests.run_valuation(record_id, batch)
    assert guests._photo_memory_used == before
    assert case.valuate.call_count == 2
    assert all(row.status == 'ready' for row in module.GuestValuation.query.all())


def test_rejected_submission_releases_buffer_and_marks_failed(guest):
    case, _ = guest
    before = guests._photo_memory_used
    with patch('valuator_client.queue_valuator_task', return_value=False):
        assert case.submit().status_code == 200
    assert guests._photo_memory_used == before
    assert case.record().status == 'failed'
    case.valuate.assert_not_called()


def test_missing_record_releases_buffer_without_provider_call(guest):
    case, _ = guest
    before = guests._photo_memory_used
    batch = guests._retain_photos([('x.jpg', b'example')])
    guests.run_valuation(999999, batch)
    assert batch == [] and guests._photo_memory_used == before
    case.valuate.assert_not_called()


def test_completed_record_releases_unused_buffer_without_second_valuation(guest):
    case, _ = guest
    assert case.submit().status_code == 200
    case.run_jobs()
    before = guests._photo_memory_used
    batch = guests._retain_photos([('x.jpg', b'example')])
    guests.run_valuation(case.record().id, batch)
    assert batch == [] and guests._photo_memory_used == before
    assert case.valuate.call_count == 1


def test_encoding_failure_releases_buffer_and_marks_failed(guest):
    case, _ = guest
    jobs = []
    before = guests._photo_memory_used
    with patch('valuator_client.queue_valuator_task', lambda fn, *args: jobs.append(args) or True):
        assert case.submit().status_code == 200
    with patch.object(guests, '_encode_photos', side_effect=RuntimeError('synthetic failure')):
        guests.run_valuation(*jobs.pop())
    assert guests._photo_memory_used == before
    assert case.record().status == 'failed'
    case.valuate.assert_not_called()


def test_api_failure_does_not_keep_originals(guest):
    case, _ = guest
    jobs = []
    before = guests._photo_memory_used
    case.valuate.return_value = {'success': False}
    with patch('valuator_client.queue_valuator_task', lambda fn, *args: jobs.append(args) or True):
        assert case.submit().status_code == 200
    guests.run_valuation(*jobs.pop())
    assert guests._photo_memory_used == before
    assert case.record().status == 'failed'


def test_photo_budget_boundary_and_idempotent_release():
    before = guests._photo_memory_used
    with patch.object(guests, 'PHOTO_MEMORY_BUDGET', before + 10):
        batch = guests._retain_photos([('one.jpg', b'12345'), ('two.jpg', b'67890')])
        assert batch == [b'12345', b'67890']
        assert guests._retain_photos([('extra.jpg', b'x')]) is None
        guests._release_retained_photos(batch)
        guests._release_retained_photos(batch)
        assert guests._photo_memory_used == before
        assert guests._retain_photos([('large.jpg', b'12345678901')]) is None
        assert guests._photo_memory_used == before


def test_concurrent_admission_never_exceeds_photo_budget():
    before = guests._photo_memory_used
    batches = []
    try:
        with patch.object(guests, 'PHOTO_MEMORY_BUDGET', before + 30):
            with ThreadPoolExecutor(max_workers=12) as pool:
                batches = list(pool.map(lambda _: guests._retain_photos([('one.jpg', b'1234567890')]), range(12)))
            assert sum(batch is not None for batch in batches) == 3
            assert guests._photo_memory_used == before + 30
    finally:
        for batch in batches:
            guests._release_retained_photos(batch)
    assert guests._photo_memory_used == before


def test_dropped_or_cancelled_handoff_releases_reservation():
    before = guests._photo_memory_used
    batch = guests._retain_photos([('one.jpg', b'abc')])
    assert guests._photo_memory_used == before + 3
    del batch
    gc.collect()
    assert guests._photo_memory_used == before


def test_memory_allocation_failure_uses_disk_without_leaking_reservation():
    before = guests._photo_memory_used
    with patch.object(guests, '_RetainedPhotos', side_effect=MemoryError('synthetic allocation failure')):
        assert guests._retain_photos([('one.jpg', b'abc')]) is None
    assert guests._photo_memory_used == before


def test_plain_photo_list_is_not_mutated_by_cleanup():
    photos = [b'one', b'two']
    guests._release_retained_photos(photos)
    assert photos == [b'one', b'two']
