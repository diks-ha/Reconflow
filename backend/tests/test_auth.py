from fastapi import HTTPException
import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import get_current_user
from app.api.routes.auth import login, me
from app.core.security import decode_access_token
from app.schemas.auth import LoginRequest


def test_postgres_urls_select_installed_psycopg_driver():
    from app.core.config import Settings

    assert Settings.model_validate({"jwt_secret_key": "x" * 32, "database_url": "postgres://db/app"}).database_url == "postgresql+psycopg://db/app"
    assert Settings.model_validate({"jwt_secret_key": "x" * 32, "database_url": "postgresql://db/app"}).database_url == "postgresql+psycopg://db/app"


def test_login_and_me_returns_identity_and_roles(db):
    response = login(LoginRequest(email="exec@example.com", password="correct-horse-battery"), db)
    subject = decode_access_token(response.access_token)["sub"]
    profile = me(get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=response.access_token), db))
    assert profile.email == "exec@example.com"
    assert profile.roles == ["FINANCE_EXECUTIVE"]
    assert "password" not in profile.model_dump()
    assert subject == profile.id


def test_login_rejects_bad_password(db):
    with pytest.raises(HTTPException) as error:
        login(LoginRequest(email="exec@example.com", password="wrong-password"), db)
    assert error.value.status_code == 401


def test_login_normalizes_email(db):
    response = login(LoginRequest(email="EXEC@example.com", password="correct-horse-battery"), db)
    assert decode_access_token(response.access_token)["sub"]


def test_login_validates_email_and_bcrypt_byte_limit():
    with pytest.raises(ValueError):
        LoginRequest(email="not-an-email", password="secret")
    with pytest.raises(ValueError):
        LoginRequest(email="valid@example.com", password="é" * 37)


def test_current_user_rejects_invalid_token(db):
    with pytest.raises(HTTPException) as error:
        get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid"), db)
    assert error.value.status_code == 401

