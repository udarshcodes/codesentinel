import os
import pytest
from api.db import get_connection, DBConnection, DBCursor

def test_db_connection_switching():
    # Store originals
    orig_db_url = os.environ.get("DATABASE_URL")
    
    try:
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
            
        conn_sqlite = get_connection()
        assert not conn_sqlite.is_postgres
        import sqlite3
        assert isinstance(conn_sqlite.conn, sqlite3.Connection)
        
        # Only if psycopg2 is installed (it should be)
        try:
            import psycopg2
        except ImportError:
            pytest.skip("psycopg2 not installed")
            
        # We don't need a real working PG for this specific instantiation test
        # if we mock psycopg2.connect, or if we just check is_postgres logic.
        # But wait, the instantiation will actually try to connect if it's set.
        # Let's mock psycopg2.connect to avoid actually needing a DB for this quick test.
        import unittest.mock as mock
        with mock.patch("psycopg2.connect") as mock_connect:
            mock_connect.return_value = mock.MagicMock()
            
            os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
            conn_pg = get_connection()
            assert conn_pg.is_postgres
            assert mock_connect.called
            
        # Test back to SQLite
        del os.environ["DATABASE_URL"]
        conn_sqlite_2 = get_connection()
        assert not conn_sqlite_2.is_postgres
        
    finally:
        # Restore
        if orig_db_url is not None:
            os.environ["DATABASE_URL"] = orig_db_url
        elif "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
