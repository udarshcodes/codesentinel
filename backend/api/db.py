import sqlite3
import os
import re

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "codesentinel.db"))
DATABASE_URL = os.getenv("DATABASE_URL")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

_pg_pool = None

def get_pg_pool():
    global _pg_pool
    if _pg_pool is None and DATABASE_URL:
        import psycopg2.pool
        # Use ThreadedConnectionPool since the backend uses thread pools for sync execution in FastAPI
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, DATABASE_URL)
    return _pg_pool

def _convert_placeholders(query: str) -> str:
    # Safely convert ? to %s ignoring ? inside single or double quotes
    pattern = r"'[^']*'|\"[^\"]*\"|\?"
    return re.sub(pattern, lambda m: "%s" if m.group(0) == "?" else m.group(0), query)

class DBConnection:
    def __init__(self):
        db_url = os.getenv("DATABASE_URL")
        environment = os.getenv("ENVIRONMENT", "development")
        
        if environment == "production" and not db_url:
            raise RuntimeError("FATAL: DATABASE_URL must be configured in production for durable state.")
            
        self.is_postgres = bool(db_url)
        self.pooled_conn = None
        if self.is_postgres:
            pool = get_pg_pool()
            self.conn = pool.getconn()
            self.pooled_conn = self.conn
        else:
            # Dynamically read DB_PATH to support test isolation (isolated_db),
            # but fallback to the module-level DB_PATH if os.environ is cleared (e.g. patch.dict clear=True).
            resolved_db_path = os.getenv("DB_PATH") or DB_PATH
            self.conn = sqlite3.connect(resolved_db_path, timeout=10.0)
            
    def cursor(self):
        return DBCursor(self.conn.cursor(), self.is_postgres)
        
    def commit(self):
        self.conn.commit()
        
    def rollback(self):
        self.conn.rollback()
        
    def close(self):
        if self.is_postgres and self.pooled_conn:
            pool = get_pg_pool()
            pool.putconn(self.pooled_conn)
            self.pooled_conn = None
            self.conn = None
        elif self.conn:
            self.conn.close()
            self.conn = None

    def execute(self, query, params=None):
        if self.is_postgres and query.strip().upper() == "BEGIN EXCLUSIVE":
            # Backward compatibility
            query = "BEGIN"
        c = self.cursor()
        c.execute(query, params)
        return c

    def transaction(self):
        """
        Starts a transaction.
        - PostgreSQL: Uses 'BEGIN', implicitly utilizing psycopg2's transaction block.
        - SQLite: Uses 'BEGIN EXCLUSIVE' to explicitly lock the database for writes,
          preventing SQLITE_BUSY under heavy concurrency.
        """
        if self.is_postgres:
            self.execute("BEGIN")
        else:
            self.execute("BEGIN EXCLUSIVE")
            
    def for_update(self, query):
        """
        Engine-specific row locking.
        - PostgreSQL: Appends 'FOR UPDATE' to the query to serialize concurrent accesses.
        - SQLite: Returns the query unchanged, as 'BEGIN EXCLUSIVE' already provides
          database-level locking.
        """
        if self.is_postgres:
            return query + " FOR UPDATE"
        return query

class DBCursor:
    def __init__(self, cursor, is_postgres):
        self.cursor = cursor
        self.is_postgres = is_postgres
        
    def execute(self, query, params=None):
        if self.is_postgres:
            query = _convert_placeholders(query)
            if query.strip().upper() == "BEGIN EXCLUSIVE":
                query = "BEGIN"
            
        if params is None:
            self.cursor.execute(query)
        else:
            self.cursor.execute(query, params)
            
    def for_update(self, query):
        """
        Engine-specific row locking wrapper for the cursor.
        See DBConnection.for_update for details.
        """
        if self.is_postgres:
            return query + " FOR UPDATE"
        return query
            
    def fetchone(self):
        return self.cursor.fetchone()
        
    def fetchall(self):
        return self.cursor.fetchall()
        
    @property
    def rowcount(self):
        return self.cursor.rowcount

def get_connection():
    return DBConnection()
