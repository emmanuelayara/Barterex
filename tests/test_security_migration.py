import importlib.util
import unittest
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app import app


class SecurityMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_existing_credits_and_prepares_security_guards(self):
        engine = sa.create_engine('sqlite:///:memory:')
        with engine.begin() as connection:
            for statement in [
                'CREATE TABLE "user" (id INTEGER PRIMARY KEY, credits INTEGER, two_factor_enabled BOOLEAN, two_factor_secret VARCHAR(32))',
                'CREATE TABLE payment (id INTEGER PRIMARY KEY)',
                'CREATE TABLE credit_transaction (id INTEGER PRIMARY KEY, amount INTEGER)',
                'CREATE TABLE referral (id INTEGER PRIMARY KEY, referred_user_id INTEGER, item_upload_bonus_earned BOOLEAN)',
                'CREATE TABLE item (id INTEGER PRIMARY KEY, uploaded_by_id INTEGER, is_approved BOOLEAN)',
                'CREATE TABLE user_security (id INTEGER PRIMARY KEY, two_factor_enabled BOOLEAN, two_factor_secret VARCHAR(32))',
                "INSERT INTO \"user\" VALUES (1, 1500, 1, 'old-unverified-secret')",
                'INSERT INTO credit_transaction VALUES (1, 500)',
                'INSERT INTO referral VALUES (1, 1, 0)',
                'INSERT INTO item VALUES (1, 1, 1)',
                "INSERT INTO user_security VALUES (1, 1, 'old-unverified-secret')",
            ]:
                connection.execute(sa.text(statement))
            path = Path(app.root_path) / 'migrations' / 'versions' / 'harden_account_payment_security.py'
            spec = importlib.util.spec_from_file_location('security_migration', path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            self.assertEqual(connection.execute(sa.text('SELECT credits FROM "user"')).scalar(), 1500)
            self.assertEqual(connection.execute(sa.text('SELECT amount FROM credit_transaction')).scalar(), 500)
            self.assertFalse(connection.execute(sa.text('SELECT two_factor_enabled FROM "user"')).scalar())
            self.assertIsNone(connection.execute(sa.text('SELECT two_factor_secret FROM user_security')).scalar())
            self.assertTrue(connection.execute(sa.text('SELECT item_upload_qualified FROM referral')).scalar())
            inspector = sa.inspect(connection)
            for table, field in [('user', 'auth_token'), ('user', 'verified_identity_hash'), ('credit_transaction', 'payment_id')]:
                self.assertTrue(any(constraint['column_names'] == [field] for constraint in inspector.get_unique_constraints(table)))
        engine.dispose()
