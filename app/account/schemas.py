from datetime import datetime
from pydantic import BaseModel


class AccountResponse(BaseModel):
    id: int
    account_hash: str
    account_number: str | None
    account_type: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
