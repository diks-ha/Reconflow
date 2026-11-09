from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


CLAIM_STATUSES = {"OPEN", "UNDER_REVIEW", "SUBMITTED", "RESOLVED", "REJECTED"}


class ClaimStatusUpdate(BaseModel):
    status: str
    recovered_amount: Decimal | None = Field(default=None, ge=0)
    assigned_reviewer_id: UUID | None = None

    @model_validator(mode="after")
    def validate_status(self):
        self.status = self.status.upper()
        if self.status not in CLAIM_STATUSES:
            raise ValueError("Unsupported claim status")
        return self


class ClaimNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def strip_note(self):
        self.note = self.note.strip()
        if not self.note:
            raise ValueError("Note cannot be blank")
        return self


class ClaimResponse(BaseModel):
    id: UUID
    partner_id: UUID | None
    order_id: str
    category: str
    amount: Decimal
    recovered_amount: Decimal
    status: str
    created_at: datetime
    updated_at: datetime
