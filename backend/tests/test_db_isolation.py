import os
import unittest
from unittest.mock import patch
from api.db import get_connection

class TestDBIsolation(unittest.TestCase):
    def test_db_path_survives_environ_clear(self):
        """
        Regression test: When os.environ is cleared by another test (e.g., to test missing webhooks),
        the DB_PATH must fall back to the test fixture's module-level snapshot,
        NOT the production/fallback host path which might be read-only.
        """
        # Ensure we can establish a connection and write even when os.environ is empty
        with patch.dict(os.environ, clear=True):
            conn = get_connection()
            # If the database was accidentally mapped to a readonly host volume, this will raise OperationalError
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS isolation_test (id INTEGER PRIMARY KEY)")
            c.execute("INSERT INTO isolation_test DEFAULT VALUES")
            conn.commit()
            
            c.execute("SELECT COUNT(*) FROM isolation_test")
            count = c.fetchone()[0]
            self.assertGreaterEqual(count, 1)
            
            conn.close()
