from pydantic import BaseModel, ConfigDict, Field, field_validator


class OfferWithdrawalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A withdrawal reason is required")
        return value
