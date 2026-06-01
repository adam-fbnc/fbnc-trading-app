from datetime import datetime
from pydantic import BaseModel


class StreamStatusResponse(BaseModel):
    running: bool
    started_at: datetime | None
    last_message_at: datetime | None
    subscriptions: dict[str, list[str]]


class SymbolsRequest(BaseModel):
    symbols: list[str]


class QuoteCacheResponse(BaseModel):
    symbol: str
    data: dict
