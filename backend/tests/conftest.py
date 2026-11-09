import os
import shutil
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-longer-than-32-characters")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.database.base import Base
from app.models.role import Role
from app.models.user import User, UserRole

TEST_ENGINE = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=TEST_ENGINE, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def writable_tmp_path():
    path = Path(__file__).resolve().parents[1] / ".test-storage" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture()
def db():
    Base.metadata.create_all(TEST_ENGINE)
    session = TestingSession()
    executive_role = Role(name="FINANCE_EXECUTIVE", description="Finance Executive")
    cofounder_role = Role(name="FINANCE_COFOUNDER", description="Finance Co-founder")
    session.add_all([executive_role, cofounder_role])
    session.flush()
    executive = User(
        email="exec@example.com", full_name="Finance Executive", password_hash=hash_password("correct-horse-battery")
    )
    cofounder = User(
        email="founder@example.com", full_name="Finance Co-founder", password_hash=hash_password("correct-horse-battery")
    )
    session.add_all([executive, cofounder])
    session.flush()
    session.add_all([
        UserRole(user_id=executive.id, role_id=executive_role.id),
        UserRole(user_id=cofounder.id, role_id=cofounder_role.id),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(TEST_ENGINE)

