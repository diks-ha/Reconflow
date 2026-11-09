from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class RateCardCreate(BaseModel):
    channel: str = Field(min_length=1, max_length=80)
    courier_partner: str = Field(min_length=1, max_length=120)
    min_weight: Decimal = Field(ge=0)
    max_weight: Decimal | None = Field(default=None, ge=0)
    forward_fee: Decimal = Field(ge=0)
    return_fee: Decimal = Field(default=Decimal("0.00"), ge=0)
    cod_fee: Decimal = Field(default=Decimal("0.00"), ge=0)
    fixed_charge: Decimal = Field(default=Decimal("0.00"), ge=0)
    percentage_charge: Decimal = Field(default=Decimal("0.0000"), ge=0)
    effective_from: date
    effective_to: date | None = None
    source_note: str = Field(default="Configured rate card", min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_range(self):
        if self.max_weight is not None and self.max_weight < self.min_weight:
            raise ValueError("max_weight must be greater than or equal to min_weight")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be before effective_from")
        return self


class RateCardResponse(RateCardCreate):
    id: UUID
    is_active: bool
