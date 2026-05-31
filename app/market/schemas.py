from datetime import date, datetime
from pydantic import BaseModel


class SessionWindow(BaseModel):
    start: str
    end: str


class MarketHoursResponse(BaseModel):
    market: str
    date: date
    is_open: bool
    session_hours: dict | None
    fetched_at: datetime

    model_config = {"from_attributes": True}
