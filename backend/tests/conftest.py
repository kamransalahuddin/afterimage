from __future__ import annotations

import base64
import os
import secrets
import warnings

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)

TEST_DB = os.environ.get("AFTERIMAGE_TEST_DATABASE_URL", "postgresql+psycopg://localhost/afterimage_test")


@pytest.fixture(scope="session")
def settings(tmp_path_factory):
    from app.config import Settings

    return Settings(
        env="test",
        database_url=TEST_DB,
        storage_dir=tmp_path_factory.mktemp("storage"),
        master_key=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        audit_secret=secrets.token_urlsafe(16),
        admin_token=secrets.token_urlsafe(16),
        cleanup_interval_seconds=0,
        public_base_url="http://testserver",
    )


@pytest.fixture(scope="session")
def app(settings):
    from app.db import get_engine
    from app.main import create_app
    from app.models.orm import Base

    application = create_app(settings)
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    yield application


@pytest.fixture(autouse=True)
def _clean(request):
    from app.services.ratelimit import limiter

    limiter.reset()
    yield
    if "app" in request.fixturenames:
        from sqlalchemy import text

        from app.db import get_engine

        with get_engine().begin() as conn:
            for table in ("audit_events", "shares", "artifacts", "detections", "processing_sessions"):
                conn.execute(text(f"DELETE FROM {table}"))
        store = request.getfixturevalue("app").state.services.store
        for bucket in ("originals", "artifacts"):
            for key in store.keys(bucket):
                store.delete(bucket, key)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
def svc(app):
    return app.state.services


@pytest.fixture
def db(app):
    from app.db import session_factory

    s = session_factory()()
    yield s
    s.close()
