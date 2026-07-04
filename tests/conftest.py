"""
tests/conftest.py — Shared pytest fixtures.

`fixtures_dir` builds the standard PDF fixture set (see
tests/fixtures/generate_fixtures.py) once per test session into a temp
directory, so no test fixture files are committed to the repo.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))  # so `import fixtures.generate_fixtures` works
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # repo root, so `import pharmagpt` works

from fixtures.generate_fixtures import build_all  # noqa: E402


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory) -> dict:
    """Build every standard PDF fixture once per test session.

    Returns {filename: absolute_path}, e.g. fixtures_dir["small.pdf"].
    """
    out_dir = tmp_path_factory.mktemp("pdf_fixtures")
    return build_all(str(out_dir))


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Point pharmagpt.database at a throwaway SQLite file for this test and
    initialize its schema. Restores the original path automatically."""
    from pharmagpt import database as db

    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db()
    return test_db


@pytest.fixture()
def client(db_path):
    """Flask test client wired to the db_path fixture's throwaway database.
    pharmagpt.app may already be imported from an earlier test — that's fine,
    since every DB call resolves db.DB_PATH dynamically at call time rather
    than caching it, so each test still gets full isolation."""
    import pharmagpt.app as appmod

    return appmod.app.test_client()
