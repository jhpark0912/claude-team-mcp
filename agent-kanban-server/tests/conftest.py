"""Shared test fixtures."""

import sqlite3
from pathlib import Path

import pytest

from agent_kanban import db


@pytest.fixture
def conn(tmp_path: Path, monkeypatch):
    """Create a fresh in-memory DB connection for each test."""
    test_db = tmp_path / "test_kanban.db"
    monkeypatch.setattr(db, "SQLITE_PATH", test_db)
    connection = db.get_connection()
    db.init_db(connection)
    db.migrate_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def project(conn):
    """Create a test project."""
    return db.init_project(conn, "Test Project")
