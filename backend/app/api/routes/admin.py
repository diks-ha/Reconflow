from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.session import get_db
from app.models.role import Role
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["administration"])


@router.get("/roles")
def list_roles(
    _: User = Depends(require_roles("FINANCE_COFOUNDER")),
    db: Session = Depends(get_db),
) -> list[dict[str, str]]:
    return [{"name": role.name, "description": role.description} for role in db.query(Role).order_by(Role.name)]


@router.get("/users")
def list_users(
    _: User = Depends(require_roles("FINANCE_COFOUNDER")),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Read-only user directory for finance co-founders; never exposes credentials."""
    users = db.query(User).order_by(User.email).all()
    return [
        {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "roles": sorted({association.role.name for association in user.roles}),
        }
        for user in users
    ]

