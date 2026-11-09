import pytest
from fastapi import HTTPException

from app.api.deps import require_roles
from app.models.user import User


def test_cofounder_can_access_cofounder_dependency(db):
    founder = db.query(User).filter_by(email="founder@example.com").one()
    authorized = require_roles("FINANCE_COFOUNDER")
    assert authorized(founder).id == founder.id


def test_finance_executive_is_denied_cofounder_permission(db):
    executive = db.query(User).filter_by(email="exec@example.com").one()
    authorized = require_roles("FINANCE_COFOUNDER")
    with pytest.raises(HTTPException) as error:
        authorized(executive)
    assert error.value.status_code == 403


def test_either_role_can_access_shared_finance_permission(db):
    executive = db.query(User).filter_by(email="exec@example.com").one()
    authorized = require_roles("FINANCE_EXECUTIVE", "FINANCE_COFOUNDER")
    assert authorized(executive).id == executive.id

