import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from main import app

# IMPORTANT:
# - If your routers define get_db in routers.users / routers.chat, we override both.
# - If your get_db lives elsewhere, adjust these imports accordingly.
import routers.users as users_router
import routers.chat as chat_router

TEST_DB_URL = "sqlite:///./test_identity.db"


@pytest.fixture(scope="session")
def engine():
    # ensure clean file
    if os.path.exists("test_identity.db"):
        os.remove("test_identity.db")

    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(bind=engine)
    yield engine

    # cleanup
    engine.dispose()
    if os.path.exists("test_identity.db"):
        os.remove("test_identity.db")


@pytest.fixture()
def db_session(engine):
    """
    Create a new database session for a test, wrapped in a transaction
    that is rolled back at the end of the test.
    """
    connection = engine.connect()
    transaction = connection.begin()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    # Override DB dependency used by routers
    app.dependency_overrides[users_router.get_db] = override_get_db
    app.dependency_overrides[chat_router.get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
