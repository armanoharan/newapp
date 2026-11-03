import os

# Must be set before the app is imported. TEST_DATABASE_URL lets CI run against Postgres.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite://")
os.environ.pop("API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from api.main import app

    # One client for the whole run: the MCP session manager can only start once per process.
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fresh_db():
    from api.db import reset_db

    reset_db()
    yield
