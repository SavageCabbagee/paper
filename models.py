from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Account(SQLModel, table=True):
    telegram_id: int = Field(primary_key=True)
    sol_balance: float


class Position(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(foreign_key="account.telegram_id")
    token_address: str
    quantity: float
    entry_price: float
    entry_mcap: float
