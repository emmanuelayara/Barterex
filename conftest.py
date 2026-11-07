"""Keep pytest isolated from persistent databases and outgoing email."""

import os

import pytest

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'


def _require_in_memory_database():
    from app import app, db

    with app.app_context():
        if any(
            engine.url.get_backend_name() != 'sqlite'
            or engine.url.database not in (None, '', ':memory:')
            for engine in db.engines.values()
        ):
            raise pytest.UsageError(
                'Tests require in-memory SQLite. Refusing to run against a persistent database. '
                'Start pytest in a fresh process so the test database is selected before app import.'
            )
    app.config['MAIL_SUPPRESS_SEND'] = True


def pytest_sessionstart(session):
    _require_in_memory_database()


def pytest_runtest_setup(item):
    _require_in_memory_database()
