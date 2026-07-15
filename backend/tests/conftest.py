"""
Shared fixtures.

Tests run against a SEPARATE database (qtech_resolver_test) which is created on
demand and rebuilt for every test. The dev database is never touched — a test
suite that can destroy your working data is a test suite you stop running.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.dependencies import get_db
from app.main import app
from app import models

TEST_DB = "qtech_resolver_test"
TEST_URL = settings.DATABASE_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"


@pytest.fixture(autouse=True)
def _test_signup_domain(monkeypatch):
    """Tests must not depend on the developer's .env.

    Real deployments close self-registration (ALLOWED_SIGNUP_DOMAINS), which
    would otherwise block the fixtures that register @qtechtest.io users. Tests
    that specifically exercise the domain gate override this.
    """
    monkeypatch.setattr(settings, "ALLOWED_SIGNUP_DOMAINS", "qtechtest.io")
    yield


@pytest.fixture(scope="session", autouse=True)
def _create_test_database():
    """CREATE DATABASE can't run inside a transaction, hence AUTOCOMMIT."""
    admin_url = settings.DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))

    engine.dispose()
    yield


@pytest.fixture(scope="session")
def engine(_create_test_database):
    eng = create_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    """A clean schema per test. Slower than a transaction rollback, but it means
    one test can never leak state into the next — including sequence values,
    which a rollback would not reset."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()

    # Every test runs inside one implicit organization -- the multi-org signup
    # flow (create-org vs join-org) has its own tests once it exists; these
    # tests are about the app's behaviour WITHIN a tenant, so one is seeded up
    # front the same way the SLA reference data below is.
    org = models.Organization(
        name="QTech Test Org", key_prefix="QTR", join_code="TESTJOIN1",
    )
    session.add(org)
    session.commit()
    session.refresh(org)

    # The SLA policies are reference data seeded by a migration in dev; the
    # schema alone doesn't carry them, so tests must set them up explicitly.
    session.add_all([
        models.SLAPolicy(organization_id=org.id, priority=models.TicketPriority.HIGHEST, threshold_hours=4),
        models.SLAPolicy(organization_id=org.id, priority=models.TicketPriority.HIGH, threshold_hours=8),
    ])
    session.commit()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    """TestClient wired to the test session, so a request and the assertions
    afterwards see the same data."""
    def override_get_db():
        try:
            yield db
        finally:
            pass  # the db fixture owns the session lifecycle

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------- users

# Must match the org the `db` fixture creates -- self-registration is now
# always "join a specific organization", so every test user joins this one via
# the same search-then-join-code flow a real signup uses.
TEST_ORG_NAME = "QTech Test Org"
TEST_ORG_JOIN_CODE = "TESTJOIN1"


def _register(client, email, name, password="password123"):
    orgs = client.get("/organizations/search", params={"name": TEST_ORG_NAME}).json()
    assert orgs, "the db fixture should have already created the test organization"
    r = client.post(
        "/auth/signup/join",
        json={
            "email": email,
            "full_name": name,
            "password": password,
            "organization_id": orgs[0]["id"],
            "join_code": TEST_ORG_JOIN_CODE,
        },
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return me.json()


def _token(client, email, password="password123"):
    r = client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin(client):
    """The first account registered always becomes the admin."""
    user = _register(client, "admin@qtechtest.io", "Ada Admin")
    return {**user, "token": _token(client, "admin@qtechtest.io")}


@pytest.fixture()
def manager(client, admin, db):
    user = _register(client, "manager@qtechtest.io", "Mo Manager")
    r = client.patch(
        f"/users/{user['id']}/role", json={"role": "manager"}, headers=auth(admin["token"])
    )
    assert r.status_code == 200, r.text
    return {**r.json(), "token": _token(client, "manager@qtechtest.io")}


@pytest.fixture()
def dev(client, admin):
    user = _register(client, "dev@qtechtest.io", "Dev Developer")
    return {**user, "token": _token(client, "dev@qtechtest.io")}


@pytest.fixture()
def dev2(client, admin):
    user = _register(client, "dev2@qtechtest.io", "Sam Second")
    return {**user, "token": _token(client, "dev2@qtechtest.io")}


# ---------------------------------------------------------------- data

@pytest.fixture()
def label(client, dev):
    r = client.post(
        "/labels/", json={"name": "Payments", "color": "#10B981"}, headers=auth(dev["token"])
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def component(client, manager):
    r = client.post(
        "/components/",
        json={"name": "OTRAMS-Booking", "description": "Booking engine", "color": "#3E7BFA"},
        headers=auth(manager["token"]),
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def make_ticket(client, admin):
    """Factory — most tests want a ticket with one or two fields tweaked."""
    def _make(token=None, **fields):
        payload = {"title": "A ticket", **fields}
        r = client.post("/tickets/", json=payload, headers=auth(token or admin["token"]))
        assert r.status_code == 201, r.text
        return r.json()

    return _make
