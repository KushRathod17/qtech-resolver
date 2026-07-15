"""
Audit items 3 and 4: registration lockdown, login throttling, and authenticated
file serving.

Both were real data-exposure holes:
  * ANYONE on the internet could self-register and read every ticket, every
    client name and every attachment.
  * Every attachment and avatar was served with NO AUTHENTICATION at all.
"""
import pytest

from app.config import settings
from app.routers.auth import login_limiter
from tests.conftest import auth, _register, _token, TEST_ORG_NAME, TEST_ORG_JOIN_CODE


@pytest.fixture(autouse=True)
def _clean_limiter():
    """One test's failed logins must not throttle the next."""
    login_limiter.clear()
    yield
    login_limiter.clear()


@pytest.fixture()
def open_to_qtech(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_SIGNUP_DOMAINS", "qtechsoftware.com")
    yield


@pytest.fixture()
def signup_closed(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_SIGNUP_DOMAINS", "")
    yield


def _join(client, email, password="password123", join_code=TEST_ORG_JOIN_CODE):
    """Same two-step flow a real signup uses: find the org by name, then the
    join code is what actually gets you in."""
    orgs = client.get("/organizations/search", params={"name": TEST_ORG_NAME}).json()
    org_id = orgs[0]["id"] if orgs else None
    return client.post(
        "/auth/signup/join",
        json={
            "email": email, "full_name": "Someone", "password": password,
            "organization_id": org_id, "join_code": join_code,
        },
    )


def _create_org(client, org_name, email, password="password123", key_prefix="TST"):
    return client.post(
        "/auth/signup/organization",
        json={
            "email": email, "full_name": "Someone", "password": password,
            "organization_name": org_name, "key_prefix": key_prefix,
        },
    )


def _role_of(client, token):
    return client.get("/auth/me", headers=auth(token)).json()["role"]


# ---------------------------------------------------------------- registration

def test_creating_a_new_organization_is_always_allowed(client, signup_closed):
    """Starting your own workspace has no domain gate at all — there's nothing
    to protect yet, since the org doesn't exist until this call creates it.
    Its founder becomes its admin."""
    r = _create_org(client, "Founder Inc", "founder@anywhere.io")
    assert r.status_code == 201
    token = r.json()["access_token"]
    assert _role_of(client, token) == "admin"


def test_with_no_allowed_domains_joining_an_org_is_CLOSED(client, admin, signup_closed):
    """THE HOLE: this used to return 201 for anyone on the internet."""
    r = _join(client, "randomer@gmail.com")
    assert r.status_code == 403
    assert "sign up" in r.json()["detail"].lower()


def test_an_outside_domain_cannot_join(client, admin, open_to_qtech):
    r = _join(client, "attacker@evil.example")
    assert r.status_code == 403
    # Says which domains ARE allowed: it isn't a secret, and a vague error just
    # creates a support ticket for the thing meant to be self-service.
    assert "qtechsoftware.com" in r.json()["detail"]


def test_an_allowed_domain_can_join(client, admin, open_to_qtech):
    r = _join(client, "newhire@qtechsoftware.com")
    assert r.status_code == 201
    assert _role_of(client, r.json()["access_token"]) == "developer"   # never an admin, admin already exists


def test_the_domain_check_is_case_insensitive(client, admin, open_to_qtech):
    assert _join(client, "Shouty@QTechSoftware.COM").status_code == 201


def test_a_lookalike_domain_is_rejected(client, admin, open_to_qtech):
    """`evil-qtechsoftware.com` and `qtechsoftware.com.evil.io` must not pass."""
    assert _join(client, "a@evil-qtechsoftware.com").status_code == 403
    assert _join(client, "b@qtechsoftware.com.evil.io").status_code == 403


def test_a_wrong_join_code_is_rejected(client, admin, open_to_qtech):
    """Finding the org by name is not enough on its own — the code has to
    match too. Same error as a nonexistent org, so the response can't be used
    to enumerate which organizations are real."""
    r = _join(client, "someone@qtechsoftware.com", join_code="TOTALLY-WRONG")
    assert r.status_code == 400


def test_admins_can_still_add_anyone_regardless_of_domain(client, admin, open_to_qtech):
    """The domain gate is for SELF-registration. A deliberate admin decision to
    add a contractor on gmail is still allowed."""
    r = client.post(
        "/users/",
        json={
            "email": "contractor@gmail.com",
            "full_name": "Contractor",
            "temp_password": "temporary123",
        },
        headers=auth(admin["token"]),
    )
    assert r.status_code == 201


# ---------------------------------------------------------------- login throttle

def _bad_login(client, email="admin@qtechtest.io"):
    return client.post(
        "/auth/login",
        data={"username": email, "password": "wrong"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def test_repeated_failures_are_throttled(client, admin):
    """Login was completely unthrottled — five known accounts on `password123`
    are brute-forceable in seconds."""
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        assert _bad_login(client).status_code == 401

    r = _bad_login(client)
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert "too many failed" in r.json()["detail"].lower()


def test_the_throttle_blocks_the_CORRECT_password_too(client, admin):
    """Otherwise the attacker just keeps guessing until they hit it — the whole
    point is to stop the guessing, not to punish wrong answers."""
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        _bad_login(client)

    r = client.post(
        "/auth/login",
        data={"username": "admin@qtechtest.io", "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 429


def test_a_success_clears_the_slate(client, admin):
    """A user who fumbles twice then gets it right shouldn't carry strikes."""
    for _ in range(settings.LOGIN_MAX_ATTEMPTS - 1):
        _bad_login(client)

    ok = client.post(
        "/auth/login",
        data={"username": "admin@qtechtest.io", "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert ok.status_code == 200

    # Back to a full budget, not one attempt from a lockout.
    assert _bad_login(client).status_code == 401


def test_login_does_not_reveal_whether_an_email_exists(client, admin):
    """Account enumeration: 'no such user' vs 'wrong password' tells an attacker
    who works here."""
    unknown = client.post(
        "/auth/login",
        data={"username": "nobody@qtechtest.io", "password": "wrong"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    known = _bad_login(client)

    assert unknown.status_code == known.status_code == 401
    assert unknown.json()["detail"] == known.json()["detail"]


# ---------------------------------------------------------------- file serving

@pytest.fixture()
def uploaded(client, admin, make_ticket):
    t = make_ticket()
    r = client.post(
        f"/tickets/{t['id']}/attachments",
        files={"file": ("booking-log.txt", b"customer booking reference 8891", "text/plain")},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 201
    return {"ticket": t, "attachment": r.json()}


def test_an_attachment_CANNOT_be_fetched_without_a_token(client, uploaded):
    """THE HOLE: /uploads was mounted as StaticFiles — no auth at all. Anyone with
    the URL got the file, signed in or not. UUID names made it unguessable, which
    is not the same as protected."""
    r = client.get(uploaded["attachment"]["url"])   # no Authorization header
    assert r.status_code == 401


def test_an_attachment_CAN_be_fetched_with_a_token(client, admin, uploaded):
    r = client.get(uploaded["attachment"]["url"], headers=auth(admin["token"]))
    assert r.status_code == 200
    assert r.content == b"customer booking reference 8891"


def test_an_attachment_is_served_under_its_ORIGINAL_filename(client, admin, uploaded):
    r = client.get(uploaded["attachment"]["url"], headers=auth(admin["token"]))
    assert "booking-log.txt" in r.headers["content-disposition"]


def test_an_attachment_is_never_rendered_inline(client, admin, uploaded):
    """A .html or .svg upload served inline would run as script on our own
    origin — a stored XSS with a file upload as the delivery mechanism."""
    r = client.get(uploaded["attachment"]["url"], headers=auth(admin["token"]))
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_an_avatar_cannot_be_fetched_without_a_token(client, dev):
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    r = client.post(
        "/users/me/avatar",
        files={"file": ("me.png", png, "image/png")},
        headers=auth(dev["token"]),
    )
    url = r.json()["avatar_url"]

    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth(dev["token"])).status_code == 200


@pytest.mark.parametrize(
    "attack",
    [
        "../../../../.env",
        "..%2f..%2f.env",
        "....//....//.env",
    ],
)
def test_path_traversal_on_the_download_url_is_refused(client, admin, attack):
    """The filename comes straight out of the URL — it's attacker-controlled."""
    r = client.get(f"/uploads/attachments/{attack}", headers=auth(admin["token"]))
    assert r.status_code in (404, 400), f"{attack} was not refused"
    assert b"DATABASE_URL" not in r.content


def test_an_unknown_file_is_a_404_not_a_500(client, admin):
    r = client.get("/uploads/attachments/nope.txt", headers=auth(admin["token"]))
    assert r.status_code == 404
