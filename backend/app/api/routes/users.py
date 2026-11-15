from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import InvalidInputError
from app.dependencies import DB, CurrentUser
from app.guardrails.output_validation import sanitize_text
from app.observability.audit import record_audit
from app.schemas.user import UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(user: CurrentUser) -> UserOut:
    return UserOut.from_row(user)


@router.patch("/me", response_model=UserOut)
async def update_me(body: UserUpdate, user: CurrentUser, db: DB) -> UserOut:
    name = sanitize_text(body.display_name, max_length=100)
    if not name:
        raise InvalidInputError("Display name is required.")
    user.display_name = name
    await record_audit(db, event_type="user.updated", user_id=user.id, entity_type="user", entity_id=str(user.id))
    await db.commit()
    return UserOut.from_row(user)
